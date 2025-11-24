import streamlit as st
from openai import OpenAI
import json
import os
import re
from datetime import datetime, timedelta
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib.parse
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# 페이지 설정
st.set_page_config(
    page_title="오늘의 YouTube 알고리즘 탈출기",
    page_icon="🎈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 커스텀 CSS 스타일
st.markdown("""
    <style>
    .main {
        padding-top: 2rem;
    }
    .stButton>button[kind="primary"] {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        font-weight: bold;
        border-radius: 20px;
        padding: 0.5rem 2rem;
        border: none;
        transition: all 0.3s;
    }
    .stButton>button[kind="primary"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
    }
    .stButton>button[kind="secondary"] {
        border-radius: 20px;
        padding: 0.5rem 1rem;
        transition: all 0.3s;
    }
    .stButton>button[kind="secondary"]:hover {
        transform: translateY(-2px);
    }
    .keyword-input {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
    }
    .recommendation-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 15px;
        margin: 1rem 0;
        color: white;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .book-card {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        padding: 1.5rem;
        border-radius: 15px;
        margin: 1rem 0;
        color: white;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .escape-card {
        background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        padding: 1.5rem;
        border-radius: 15px;
        margin: 1rem 0;
        color: white;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    h1 {
        color: #667eea;
        text-align: center;
        margin-bottom: 2rem;
    }
    h2 {
        color: #764ba2;
        margin-top: 2rem;
        margin-bottom: 1rem;
    }
    h3 {
        color: #667eea;
    }
    .keyword-button-selected {
        background-color: var(--selected-color) !important;
        color: white !important;
        border: 2px solid var(--selected-color) !important;
        font-weight: bold !important;
    }
    .keyword-button-unselected {
        background-color: var(--bg-color) !important;
        color: var(--text-color) !important;
        border: 2px solid var(--text-color) !important;
    }
    </style>
""", unsafe_allow_html=True)

# OpenAI 클라이언트 초기화
@st.cache_resource
def init_openai_client():
    """OpenAI 클라이언트 초기화"""
    api_key = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY", None)
    if not api_key:
        st.error("⚠️ OpenAI API 키가 설정되지 않았습니다. 환경변수 OPENAI_API_KEY를 설정하거나 Streamlit secrets에 추가해주세요.")
        st.stop()
    return OpenAI(api_key=api_key)

# YouTube API 클라이언트 초기화
@st.cache_resource
def init_youtube_client():
    """YouTube API 클라이언트 초기화"""
    api_key = os.getenv("YOUTUBE_API_KEY") or st.secrets.get("YOUTUBE_API_KEY", None)
    if not api_key:
        # 세션 상태에서 확인
        if "youtube_api_key" in st.session_state and st.session_state.youtube_api_key:
            api_key = st.session_state.youtube_api_key
        else:
            return None
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        return youtube
    except Exception as e:
        st.error(f"YouTube API 초기화 오류: {str(e)}")
        return None

def search_youtube_videos(youtube_client, query, limit=5, min_duration_minutes=5, max_duration_minutes=30, min_views=500000, min_subscribers=100000, randomize=True):
    """YouTube Data API v3를 사용한 검색 (5분~30분, 조회수 50만회 이상, 구독자 10만명 이상 필터링)"""
    if not youtube_client:
        return []
    
    try:
        import random
        
        # 랜덤성을 위해 order를 다양하게 설정
        order_options = ["relevance", "viewCount", "rating", "date"]
        if randomize:
            order = random.choice(order_options)
        else:
            order = "relevance"
        
        # 더 많은 결과를 가져와서 필터링
        search_response = youtube_client.search().list(
            q=query,
            part="snippet",
            maxResults=min(50, limit * 10),  # 충분한 결과 가져오기
            type="video",
            order=order
        ).execute()
        
        videos = []
        video_ids = []
        channel_ids = []
        
        # 검색 결과에서 비디오 ID와 채널 ID 수집
        for item in search_response.get('items', []):
            video_id = item['id']['videoId']
            channel_id = item['snippet']['channelId']
            video_ids.append(video_id)
            channel_ids.append(channel_id)
        
        if not video_ids:
            return []
        
        # 비디오 상세 정보 가져오기 (조회수, 길이 등) - 배치로 처리
        videos_response = youtube_client.videos().list(
            part="contentDetails,statistics,snippet",
            id=",".join(video_ids)
        ).execute()
        
        # 채널 정보 가져오기 (구독자 수) - 배치로 처리
        unique_channel_ids = list(set(channel_ids))
        channels_response = youtube_client.channels().list(
            part="statistics",
            id=",".join(unique_channel_ids)
        ).execute()
        
        # 채널 정보를 딕셔너리로 변환
        channel_info_dict = {}
        for channel_item in channels_response.get('items', []):
            channel_info_dict[channel_item['id']] = channel_item
        
        # 비디오 정보를 딕셔너리로 변환 (빠른 조회)
        video_info_dict = {}
        for video_item in videos_response.get('items', []):
            video_info_dict[video_item['id']] = video_item
        
        # 결과 결합 및 필터링
        for item in search_response.get('items', []):
            video_id = item['id']['videoId']
            channel_id = item['snippet']['channelId']
            
            # 비디오 정보 가져오기
            video_item = video_info_dict.get(video_id)
            if not video_item:
                continue
            
            # 채널 정보 가져오기 (구독자 수 확인)
            channel_item = channel_info_dict.get(channel_id)
            subscriber_count = 0
            if channel_item:
                subscriber_count = int(channel_item['statistics'].get('subscriberCount', 0))
                if min_subscribers > 0 and subscriber_count < min_subscribers:
                    continue
            else:
                # 채널 정보를 가져올 수 없으면 구독자 수 제한이 있을 때만 스킵
                if min_subscribers > 0:
                    continue
            
            # 영상 길이 확인 (5분~30분 필터링)
            duration_iso = video_item['contentDetails'].get('duration', '')
            if duration_iso:
                duration_seconds = parse_duration_to_seconds_iso(duration_iso)
                min_duration_seconds = min_duration_minutes * 60
                max_duration_seconds = max_duration_minutes * 60
                if duration_seconds < min_duration_seconds or duration_seconds > max_duration_seconds:
                    continue
                duration_str = parse_duration(duration_iso)
            else:
                duration_str = '정보 없음'
            
            # 조회수 확인 (조건이 있을 때만)
            view_count = int(video_item['statistics'].get('viewCount', 0))
            if min_views > 0 and view_count < min_views:
                continue
            
            if view_count >= 10000:
                views_str = f"{view_count/10000:.1f}만회"
            elif view_count >= 1000:
                views_str = f"{view_count/1000:.1f}천회"
            else:
                views_str = f"{view_count}회" if view_count > 0 else "정보 없음"
            
            # 영상 정보
            title = item['snippet']['title']
            channel = item['snippet']['channelTitle']
            thumbnail = item['snippet']['thumbnails']['medium']['url']
            description = item['snippet']['description']
            url = f"https://www.youtube.com/watch?v={video_id}"
            
            videos.append({
                'title': title,
                'url': url,
                'video_id': video_id,
                'duration': duration_str,
                'views': views_str,
                'view_count': view_count,  # 정렬을 위해 원본 조회수 저장
                'thumbnail': thumbnail,
                'channel': channel,
                'channel_id': channel_id,
                'subscriber_count': subscriber_count,
                'description': description
            })
        
        # 랜덤하게 섞기
        if randomize and len(videos) > limit:
            random.shuffle(videos)
        
        # limit만큼만 반환
        return videos[:limit]
        
    except HttpError as e:
        error_content = json.loads(e.content.decode('utf-8'))
        error_message = error_content.get('error', {}).get('message', str(e))
        error_code = error_content.get('error', {}).get('code', 0)
        
        # 할당량 초과 에러 처리
        if error_code == 403 and 'quota' in error_message.lower():
            st.error("⚠️ YouTube API 일일 할당량을 초과했습니다.")
            st.warning("""
            **해결 방법:**
            1. 내일 다시 시도하세요 (할당량은 매일 자정에 리셋됩니다)
            2. Google Cloud Console에서 할당량을 늘릴 수 있습니다
            3. 여러 API 키를 번갈아 사용하세요
            """)
            return []
        else:
            st.error(f"⚠️ YouTube API 오류: {error_message}")
            return []
    except Exception as e:
        st.error(f"⚠️ YouTube 검색 오류: {str(e)}")
        return []

def parse_duration(duration_iso):
    """ISO 8601 형식의 duration을 분:초 형식으로 변환"""
    try:
        # PT1H2M10S 형식을 파싱
        hours = re.search(r'(\d+)H', duration_iso)
        minutes = re.search(r'(\d+)M', duration_iso)
        seconds = re.search(r'(\d+)S', duration_iso)
        
        h = int(hours.group(1)) if hours else 0
        m = int(minutes.group(1)) if minutes else 0
        s = int(seconds.group(1)) if seconds else 0
        
        if h > 0:
            return f"{h}시간 {m}분 {s}초"
        elif m > 0:
            return f"{m}분 {s}초"
        else:
            return f"{s}초"
    except:
        return '정보 없음'

def parse_duration_to_seconds_iso(duration_iso):
    """ISO 8601 형식의 duration을 초로 변환"""
    try:
        hours = re.search(r'(\d+)H', duration_iso)
        minutes = re.search(r'(\d+)M', duration_iso)
        seconds = re.search(r'(\d+)S', duration_iso)
        
        h = int(hours.group(1)) if hours else 0
        m = int(minutes.group(1)) if minutes else 0
        s = int(seconds.group(1)) if seconds else 0
        
        return h * 3600 + m * 60 + s
    except:
        return 0

def format_duration(duration_str):
    """영상 길이 포맷팅 (MM:SS 형식 또는 초 단위)"""
    try:
        if not duration_str or duration_str == '정보 없음':
            return '정보 없음'
        
        # MM:SS 형식인 경우
        if ':' in duration_str:
            parts = duration_str.split(':')
            if len(parts) == 2:
                minutes, seconds = int(parts[0]), int(parts[1])
                if minutes > 0:
                    return f"{minutes}분 {seconds}초"
                else:
                    return f"{seconds}초"
            elif len(parts) == 3:
                hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
                return f"{hours}시간 {minutes}분 {seconds}초"
        
        # 초 단위 숫자인 경우
        numbers = re.findall(r'\d+', duration_str)
        if numbers:
            seconds = int(numbers[0])
            minutes = seconds // 60
            secs = seconds % 60
            if minutes > 0:
                return f"{minutes}분 {secs}초"
            else:
                return f"{secs}초"
        
        return duration_str
    except:
        return duration_str if duration_str else '정보 없음'

def format_views(views_str):
    """조회수 포맷팅"""
    try:
        # 숫자만 추출
        numbers = re.findall(r'[\d.]+', views_str.replace(',', ''))
        if numbers:
            num = float(numbers[0])
            if '만' in views_str or num >= 10000:
                return f"{num/10000:.1f}만회" if num >= 10000 else views_str
            elif '천' in views_str or num >= 1000:
                return f"{num/1000:.1f}천회" if num >= 1000 else views_str
            else:
                return f"{int(num)}회"
        return views_str
    except:
        return views_str

def generate_youtube_recommendations(client, youtube_client, keywords, keyword_difficulties=None):
    """YouTube 영상 추천 생성 - 키워드를 직접 사용하여 간단하고 확실하게 검색"""
    try:
        if not youtube_client:
            st.error("⚠️ YouTube API 클라이언트가 초기화되지 않았습니다.")
            return []
        
        # 키워드 개수에 따라 영상 개수 결정
        num_keywords = len(keywords)
        if num_keywords == 1:
            videos_per_keyword = 6  # 키워드 1개: 6개
        elif num_keywords == 2:
            videos_per_keyword = 3  # 키워드 2개: 각 3개씩
        else:  # 3개 이상
            videos_per_keyword = 2  # 키워드 3개: 각 2개씩
        
        all_videos = []
        
        # 각 키워드별로 직접 검색 (키워드를 그대로 검색 쿼리로 사용)
        for keyword in keywords:
            # 키워드를 직접 검색 쿼리로 사용 (간단하고 확실한 방법)
            query = keyword
            
            # 5~30분 길이의 영상만 검색 (조회수 5만회 이상, 구독자 5만명 이상)
            videos = search_youtube_videos(
                youtube_client, 
                query, 
                limit=videos_per_keyword * 5,  # 충분히 많이 가져와서 필터링
                min_duration_minutes=5, 
                max_duration_minutes=30,
                min_views=50000,  # 조회수 5만회 이상
                min_subscribers=50000,  # 구독자 5만명 이상
                randomize=True  # 랜덤 추천
            )
            
            if videos:
                # 필요한 개수만큼만 사용
                videos = videos[:videos_per_keyword]
                # 각 영상에 키워드 정보 추가
                for video in videos:
                    video['keyword'] = keyword
                all_videos.extend(videos)
            else:
                # 영상을 찾지 못한 경우 경고 메시지
                st.warning(f"⚠️ '{keyword}' 키워드에 대한 5~30분 영상을 찾지 못했습니다.")
        
        # 중복 제거 (video_id 기준)
        seen_ids = set()
        unique_videos = []
        for video in all_videos:
            if video['video_id'] not in seen_ids:
                seen_ids.add(video['video_id'])
                unique_videos.append(video)
        
        if not unique_videos:
            st.warning("⚠️ 조건에 맞는 YouTube 영상을 찾지 못했습니다.")
            return []
        
        # 키워드별로 영상 그룹화 및 개수 제한
        videos_by_keyword = {}
        for video in unique_videos:
            keyword = video.get('keyword', keywords[0] if keywords else "일반")
            if keyword not in videos_by_keyword:
                videos_by_keyword[keyword] = []
            videos_by_keyword[keyword].append(video)
        
        # 키워드 개수에 따라 각 키워드별 영상 개수 제한
        for keyword in videos_by_keyword:
            videos_by_keyword[keyword] = videos_by_keyword[keyword][:videos_per_keyword]
        
        # 모든 영상 다시 수집
        all_videos_for_analysis = []
        for keyword_videos in videos_by_keyword.values():
            all_videos_for_analysis.extend(keyword_videos)
        
        if not all_videos_for_analysis:
            return []
        
        # OpenAI로 각 영상에 대한 설명, 난이도, 추천 이유 생성 (선택적)
        recommendations = []
        try:
            titles_list = [v['title'] for v in all_videos_for_analysis]
            keywords_str = ", ".join(keywords)
            
            # 난이도 정보 추가
            difficulty_info = ""
            if keyword_difficulties:
                difficulty_labels = ["입문", "중급", "고급"]
                difficulty_list = []
                for kw in keywords:
                    diff_idx = keyword_difficulties.get(kw, 1)
                    difficulty_list.append(f"{kw}({difficulty_labels[diff_idx]})")
                difficulty_info = f"\n사용자가 설정한 난이도: {', '.join(difficulty_list)}"
            
            analysis_prompt = f"""
다음 YouTube 영상 제목들을 분석하여 각 영상에 대한 정보를 생성해주세요.

영상 제목들:
{chr(10).join([f"{i+1}. {title}" for i, title in enumerate(titles_list)])}

키워드: {keywords_str}{difficulty_info}

사용자가 설정한 난이도를 참고하여 각 영상의 난이도를 평가하세요.

다음 JSON 형식으로 응답해주세요:
{{
    "analyses": [
        {{
            "summary": "영상 내용 요약 (2-3문장)",
            "difficulty": "입문/중급/고급 중 하나",
            "reason": "왜 이 영상을 추천하는지 한 줄 설명"
        }}
    ]
}}

analyses 배열의 순서는 영상 제목 순서와 동일해야 합니다.
JSON 형식만 반환하고, 다른 설명은 포함하지 마세요.
"""
            
            analysis_response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "당신은 교육 콘텐츠 분석 전문가입니다. 정확한 JSON 형식으로만 응답합니다."},
                    {"role": "user", "content": analysis_prompt}
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            
            analysis_content = analysis_response.choices[0].message.content
            analysis_json = json.loads(analysis_content)
            analyses = analysis_json.get("analyses", [])
        except Exception as e:
            # OpenAI 분석 실패 시 기본값 사용
            st.warning(f"영상 분석 중 오류 발생: {str(e)}. 기본 정보로 표시합니다.")
            analyses = []
        
        # 영상 정보와 분석 결과 결합
        for i, video in enumerate(all_videos_for_analysis):
            analysis = analyses[i] if i < len(analyses) else {}
            
            recommendations.append({
                'title': video['title'],
                'url': video['url'],
                'video_id': video['video_id'],
                'summary': analysis.get('summary', video.get('description', '요약 정보 없음')[:200] if video.get('description') else '학습에 도움이 되는 영상입니다.'),
                'views': video.get('views', '정보 없음'),
                'duration': video.get('duration', '정보 없음'),
                'difficulty': analysis.get('difficulty', '중급'),
                'reason': analysis.get('reason', '키워드와 관련된 학습 영상입니다.'),
                'channel': video.get('channel', ''),
                'thumbnail': video.get('thumbnail', f"https://img.youtube.com/vi/{video['video_id']}/mqdefault.jpg"),
                'keyword': video.get('keyword', keywords[0] if keywords else "일반")
            })
        
        return recommendations
        
    except Exception as e:
        error_msg = str(e)
        # 할당량 초과 에러 체크
        if 'quota' in error_msg.lower() or 'exceeded' in error_msg.lower():
            st.error("⚠️ YouTube API 일일 할당량을 초과했습니다.")
            st.warning("""
            **해결 방법:**
            1. 내일 다시 시도하세요 (할당량은 매일 자정에 리셋됩니다)
            2. Google Cloud Console에서 할당량을 늘릴 수 있습니다
            3. 여러 API 키를 번갈아 사용하세요
            """)
        else:
            st.error(f"YouTube 추천 생성 중 오류 발생: {error_msg}")
        return []

def search_book_naver(title, author=""):
    """네이버 도서 검색을 사용하여 책 정보 및 책표지 검색 (개선된 버전)"""
    try:
        # 검색 쿼리 생성 (도서명만 사용)
        query = title.strip()
        
        # 네이버 도서 검색 URL
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://search.naver.com/search.naver?where=book&query={encoded_query}"
        
        # 네이버 도서 검색 페이지 요청
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.naver.com/'
        }
        response = requests.get(search_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 네이버 도서 검색 결과에서 책표지 이미지 찾기
            # 여러 방법으로 시도
            
            # 방법 1: 네이버 책 링크에서 직접 이미지 찾기
            book_links = soup.find_all('a', href=lambda x: x and 'book.naver.com' in x)
            for link in book_links[:3]:  # 최대 3개만 확인
                try:
                    img = link.find('img')
                    if img:
                        img_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src') or img.get('data-original')
                        if img_url:
                            if img_url.startswith('//'):
                                img_url = 'https:' + img_url
                            elif img_url.startswith('/'):
                                img_url = 'https://search.naver.com' + img_url
                            if 'book' in img_url.lower() or 'cover' in img_url.lower():
                                return img_url, search_url
                except:
                    continue
            
            # 방법 2: 다양한 선택자로 이미지 찾기
            selectors = [
                'img[src*="book.naver.com"]',
                'img[data-src*="book.naver.com"]',
                'img[src*="kyobobook"]',
                'img[src*="yes24"]',
                'img[src*="aladin"]',
                'img[src*="bookcover"]',
                '.book_cover img',
                '.book_img img',
                '.cover img',
                '.book_info img',
                '.book_thumb img',
                '.thumb img',
                'img[alt*="표지"]',
                'img[alt*="책"]',
                'img[class*="book"]',
                'img[class*="cover"]',
                'img[class*="thumb"]'
            ]
            
            for selector in selectors:
                try:
                    imgs = soup.select(selector)
                    for img in imgs:
                        img_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src') or img.get('data-original')
                        if img_url:
                            # URL 정규화
                            if img_url.startswith('//'):
                                img_url = 'https:' + img_url
                            elif img_url.startswith('/'):
                                img_url = 'https://search.naver.com' + img_url
                            
                            # 책표지로 보이는 이미지인지 확인
                            if any(keyword in img_url.lower() for keyword in ['book', 'cover', 'kyobo', 'yes24', 'aladin', 'bookcover', 'thumbnail']):
                                # 너무 작은 이미지나 아이콘 제외
                                if 'icon' not in img_url.lower() and 'logo' not in img_url.lower():
                                    return img_url, search_url
                except:
                    continue
            
            # 방법 3: 모든 img 태그에서 찾기 (마지막 시도)
            for img in soup.find_all('img'):
                img_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src') or img.get('data-original')
                if img_url:
                    # URL 정규화
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    elif img_url.startswith('/'):
                        img_url = 'https://search.naver.com' + img_url
                    
                    # 책표지로 보이는 이미지인지 확인
                    if any(keyword in img_url.lower() for keyword in ['book', 'cover', 'kyobo', 'yes24', 'aladin', 'thumbnail']):
                        # 아이콘, 로고 제외
                        if 'icon' not in img_url.lower() and 'logo' not in img_url.lower():
                            return img_url, search_url
        
        return None, search_url
    except Exception as e:
        # 오류 발생 시 검색 URL만 반환
        try:
            query = title.strip()
            encoded_query = urllib.parse.quote(query)
            search_url = f"https://search.naver.com/search.naver?where=book&query={encoded_query}"
            return None, search_url
        except:
            return None, None

def search_book_cover(title, author=""):
    """네이버 도서 검색을 우선 사용, 실패 시 Google Books API 사용"""
    # 먼저 네이버 도서 검색 시도
    cover_url, naver_url = search_book_naver(title, author)
    if cover_url:
        return cover_url
    
    # 네이버 검색 실패 시 Google Books API 사용
    try:
        query = f"{title}"
        if author:
            query += f" {author}"
        
        url = "https://www.googleapis.com/books/v1/volumes"
        params = {
            "q": query,
            "maxResults": 1,
            "langRestrict": "ko"
        }
        
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("items") and len(data["items"]) > 0:
                volume_info = data["items"][0].get("volumeInfo", {})
                image_links = volume_info.get("imageLinks", {})
                if image_links:
                    cover_url = (
                        image_links.get("large") or
                        image_links.get("medium") or
                        image_links.get("small") or
                        image_links.get("thumbnail") or
                        image_links.get("smallThumbnail")
                    )
                    if cover_url:
                        cover_url = cover_url.replace("http://", "https://")
                        return cover_url
    except:
        pass
    
    return None

def generate_book_recommendations(client, keywords):
    """책 추천 생성 (키워드별로 추천, 한국어 도서 위주, 책표지 이미지 URL 포함, 키워드만 표시, 페이지수 포함)"""
    num_keywords = len(keywords)
    
    # 키워드 개수에 따라 도서 개수 결정
    if num_keywords == 1:
        # 키워드 1개: 3권
        books_per_keyword = {keywords[0]: 3}
    elif num_keywords == 2:
        # 키워드 2개: 첫 번째 2권, 두 번째 1권
        books_per_keyword = {keywords[0]: 2, keywords[1]: 1}
    else:  # 3개 이상
        # 키워드 3개: 각 1권씩
        books_per_keyword = {kw: 1 for kw in keywords[:3]}
    
    all_books = []
    
    # 각 키워드별로 도서 추천
    for keyword, num_books in books_per_keyword.items():
        prompt = f"""
다음 키워드와 관련된 학습과 성장에 도움이 되는 한국어 도서 {num_books}권을 추천해주세요.

중요: 반드시 한국어로 출판된 도서만 추천하세요. 한국 저자나 한국에서 출판된 책을 우선적으로 추천하세요.

키워드: {keyword}

다음 JSON 형식으로 응답해주세요:
{{
    "books": [
        {{
            "title": "책 제목 (한국어)",
            "author": "저자명 (한국어)",
            "keywords": ["관련 키워드1", "관련 키워드2", "관련 키워드3"],
            "pages": 300
        }}
    ]
}}

- 반드시 한국어로 출판된 도서만 추천하세요
- 한국 저자나 한국 출판사의 책을 우선적으로 추천하세요
- keywords는 책 제목과 관련된 키워드 3개를 배열로 제공하세요
- pages는 책의 페이지 수를 숫자로 제공하세요 (예: 300, 450)
- 정확히 {num_books}권만 추천하세요
JSON 형식만 반환하고, 다른 설명은 포함하지 마세요.
"""
        
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "당신은 도서 추천 전문가입니다. 정확한 JSON 형식으로만 응답합니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            json_content = json.loads(content)
            
            books = []
            if "books" in json_content:
                books = json_content["books"]
            elif isinstance(json_content, list):
                books = json_content
            else:
                for key, value in json_content.items():
                    if isinstance(value, list):
                        books = value
                        break
            
            # 각 책에 키워드 정보 추가
            for book in books:
                book['recommended_for_keyword'] = keyword
                all_books.append(book)
        
        except Exception as e:
            st.error(f"키워드 '{keyword}'에 대한 도서 추천 중 오류: {str(e)}")
            continue
    
    # 각 책에 대해 책표지 검색
    for book in all_books:
        title = book.get('title', '')
        author = book.get('author', '')
        
        # 네이버 도서 검색으로 책표지 검색
        cover_url = search_book_cover(title, author)
        if cover_url:
            book['cover_image_url'] = cover_url
        else:
            # 네이버 검색 실패 시 Google Books API 시도
            try:
                query = f"{title}"
                if author:
                    query += f" {author}"
                
                url = "https://www.googleapis.com/books/v1/volumes"
                params = {
                    "q": query,
                    "maxResults": 1,
                    "langRestrict": "ko"
                }
                
                response = requests.get(url, params=params, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("items") and len(data["items"]) > 0:
                        volume_info = data["items"][0].get("volumeInfo", {})
                        image_links = volume_info.get("imageLinks", {})
                        if image_links:
                            cover_url = (
                                image_links.get("large") or
                                image_links.get("medium") or
                                image_links.get("small") or
                                image_links.get("thumbnail") or
                                image_links.get("smallThumbnail")
                            )
                            if cover_url:
                                cover_url = cover_url.replace("http://", "https://")
                                book['cover_image_url'] = cover_url
            except:
                pass
            
            # 여전히 없으면 유관 이미지 검색 (Unsplash API 사용)
            if not book.get('cover_image_url'):
                try:
                    # 책 제목으로 관련 이미지 검색
                    unsplash_url = f"https://source.unsplash.com/400x600/?book,{urllib.parse.quote(title[:20])}"
                    book['cover_image_url'] = unsplash_url
                except:
                    # 최종 실패 시 기본 이미지
                    book['cover_image_url'] = f"https://via.placeholder.com/200x300/667eea/ffffff?text={title[:20]}"
        
        # keywords가 없으면 빈 배열로 설정
        if not book.get('keywords'):
            book['keywords'] = []
        
        # pages가 없으면 기본값 설정
        if not book.get('pages'):
            book['pages'] = 300
    
    return all_books

def generate_nickname(client, keywords):
    """키워드 기반 재치있고 유행어를 담은 문구 생성"""
    keywords_str = ", ".join([k for k in keywords if k])
    prompt = f"""
다음 키워드를 기반으로 재치있고 통상적으로 사용할 만한 유행어를 담은 "오늘의 나" 문구를 생성해주세요.

키워드: {keywords_str}

요구사항:
- 재치있고 유머러스한 표현
- 최근 유행하는 표현이나 밈 활용
- 통상적으로 사용할 만한 자연스러운 표현
- 키워드의 특성을 잘 반영
- "오늘의 나는 ~" 형식으로 시작

예시:
- AI, 머신러닝 -> "오늘의 나는 AI로 갓생 사는 개발자", "오늘의 나는 머신러닝으로 월급 올리는 직장인"
- 부동산, 국내주식 -> "오늘의 나는 부동산으로 부자 되는 투자자", "오늘의 나는 주식으로 갓생 사는 트레이더"
- 심리학, 자기계발 -> "오늘의 나는 마인드셋 바꾼 성장러", "오늘의 나는 자기계발로 인생 바꾼 사람"
- 홈트레이닝, 런닝 -> "오늘의 나는 홈트로 몸 만드는 운동러", "오늘의 나는 런닝으로 건강 챙기는 갓생러"

다음 JSON 형식으로 응답해주세요:
{{
    "nickname": "오늘의 나는 [재치있고 유행어를 담은 문구]"
}}

JSON 형식만 반환하고, 다른 설명은 포함하지 마세요.
"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 재치있고 유행어를 잘 활용하는 문구 생성 전문가입니다. 정확한 JSON 형식으로만 응답합니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.95,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        json_content = json.loads(content)
        nickname = json_content.get("nickname", "오늘의 나는 성장하는 학습자")
        # "오늘의 나는"이 없으면 추가
        if not nickname.startswith("오늘의 나는"):
            nickname = f"오늘의 나는 {nickname}"
        return nickname
    except:
        return "오늘의 나는 성장하는 학습자"

def generate_escape_recommendations(client, youtube_client, keywords):
    """알고리즘 탈출용 이색 콘텐츠 추천 - 실제 YouTube 검색 사용"""
    try:
        # 1. OpenAI로 검색 쿼리 생성 (완전히 다른 분야)
        keywords_str = ", ".join(keywords)
        query_prompt = f"""
사용자가 다음 분야를 공부하고 있습니다: {keywords_str}

이 분야와 전혀 관련 없는, 완전히 다른 영역의 YouTube 검색 쿼리 3개를 생성해주세요.
목적: 뇌 자극, 사고 확장, 알고리즘 탈출, 새로운 관점 획득

예를 들어:
- 우주, 천문학
- 자연 다큐멘터리
- 미니멀리즘 라이프스타일
- 과학 실험
- 예술, 음악
- 여행, 문화
- 요리, 수공예
등 완전히 다른 분야

다음 JSON 형식으로 응답해주세요:
{{
    "queries": [
        "검색 쿼리 1",
        "검색 쿼리 2",
        "검색 쿼리 3"
    ],
    "categories": [
        "카테고리 1",
        "카테고리 2",
        "카테고리 3"
    ]
}}

JSON 형식만 반환하고, 다른 설명은 포함하지 마세요.
"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 다양한 콘텐츠 추천 전문가입니다. 정확한 JSON 형식으로만 응답합니다."},
                {"role": "user", "content": query_prompt}
            ],
            temperature=0.8,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        json_content = json.loads(content)
        queries = json_content.get("queries", [])
        categories = json_content.get("categories", ["기타"] * len(queries))
        
        # 2. 각 쿼리로 YouTube 검색
        all_videos = []
        for i, query in enumerate(queries[:3]):
            videos = search_youtube_videos(youtube_client, query, limit=1, min_duration_minutes=5, max_duration_minutes=30)
            if videos:
                for video in videos:
                    video['category'] = categories[i] if i < len(categories) else "기타"
                all_videos.extend(videos)
        
        # 중복 제거
        seen_ids = set()
        unique_videos = []
        for video in all_videos:
            if video['video_id'] not in seen_ids:
                seen_ids.add(video['video_id'])
                unique_videos.append(video)
        
        # 3. OpenAI로 각 영상에 대한 설명과 추천 이유 생성
        if not unique_videos:
            return []
        
        titles_list = [v['title'] for v in unique_videos[:3]]
        categories_list = [v.get('category', '기타') for v in unique_videos[:3]]
        
        analysis_prompt = f"""
다음 YouTube 영상 제목들을 분석하여 각 영상에 대한 정보를 생성해주세요.

영상 제목들:
{chr(10).join([f"{i+1}. {title} (카테고리: {cat})" for i, (title, cat) in enumerate(zip(titles_list, categories_list))])}

이 영상들은 사용자가 공부하는 분야({keywords_str})와 전혀 다른 영역의 콘텐츠입니다.
목적: 뇌 자극, 사고 확장, 알고리즘 탈출

다음 JSON 형식으로 응답해주세요:
{{
    "analyses": [
        {{
            "summary": "영상 내용 요약 (2-3문장)",
            "reason": "왜 이 영상이 사고 확장에 도움이 되는지 한 줄 설명"
        }}
    ]
}}

analyses 배열의 순서는 영상 제목 순서와 동일해야 합니다.
JSON 형식만 반환하고, 다른 설명은 포함하지 마세요.
"""
        
        analysis_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 다양한 콘텐츠 분석 전문가입니다. 정확한 JSON 형식으로만 응답합니다."},
                {"role": "user", "content": analysis_prompt}
            ],
            temperature=0.8,
            response_format={"type": "json_object"}
        )
        
        analysis_content = analysis_response.choices[0].message.content
        analysis_json = json.loads(analysis_content)
        analyses = analysis_json.get("analyses", [])
        
        # 4. 영상 정보와 분석 결과 결합
        recommendations = []
        for i, video in enumerate(unique_videos[:3]):
            analysis = analyses[i] if i < len(analyses) else {}
            
            recommendations.append({
                'title': video['title'],
                'url': video['url'],
                'video_id': video['video_id'],
                'summary': analysis.get('summary', video.get('description', '요약 정보 없음')[:200]),
                'category': video.get('category', '기타'),
                'reason': analysis.get('reason', '사고 확장에 도움이 되는 영상입니다.'),
                'channel': video.get('channel', ''),
                'views': video.get('views', '정보 없음'),
                'duration': video.get('duration', '정보 없음'),
                'thumbnail': video.get('thumbnail', f"https://img.youtube.com/vi/{video['video_id']}/mqdefault.jpg"),
                'difficulty': '기타'
            })
        
        return recommendations
        
    except json.JSONDecodeError as e:
        st.error(f"JSON 파싱 오류: {str(e)}")
        return []
    except Exception as e:
        st.error(f"탈출 콘텐츠 추천 생성 중 오류 발생: {str(e)}")
        return []

def render_single_video(video, watched_key_prefix="youtube_watched"):
    """단일 YouTube 영상 카드 형식으로 표시"""
    if not video:
        return False
    
    # 시청 상태 초기화
    if watched_key_prefix not in st.session_state:
        st.session_state[watched_key_prefix] = {}
    
    video_id = video.get('video_id', '')
    thumbnail = video.get('thumbnail', '')
    if not thumbnail and video_id:
        thumbnail = f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
    
    st.image(thumbnail, use_container_width=True)
    st.markdown(f"**{video.get('title', '제목 없음')}**")
    st.markdown(f"📺 {video.get('channel', '정보 없음')}")
    st.markdown(f"⏱️ {video.get('duration', '정보 없음')} | 👁️ {video.get('views', '정보 없음')}")
    st.markdown(f"[🔗 보기]({video.get('url', '#')})")
    
    # 시청 체크박스
    watched_key = f"{watched_key_prefix}_{video_id}"
    is_watched = st.checkbox(
        "✅ 시청 완료",
        value=st.session_state[watched_key_prefix].get(video_id, False),
        key=watched_key
    )
    st.session_state[watched_key_prefix][video_id] = is_watched
    
    return is_watched

def render_youtube_table(videos, watched_key_prefix="youtube_watched"):
    """YouTube 영상 테이블 형식으로 표시 (썸네일 포함, 시청 체크박스)"""
    if not videos:
        return False
    
    # 시청 상태 초기화
    if watched_key_prefix not in st.session_state:
        st.session_state[watched_key_prefix] = {}
    
    # 테이블 데이터 준비
    for idx, video in enumerate(videos):
        video_id = video.get('video_id', f'video_{idx}')
        thumbnail = video.get('thumbnail', '')
        if not thumbnail and video_id:
            thumbnail = f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
        
        st.image(thumbnail, width=150, use_container_width=False)
        st.markdown(f"**{video.get('title', '제목 없음')}**")
        st.markdown(f"채널: {video.get('channel', '정보 없음')}")
        st.markdown(f"길이: {video.get('duration', '정보 없음')} | 조회수: {video.get('views', '정보 없음')}")
        st.markdown(f"[🔗 보기]({video.get('url', '#')})")
        
        # 시청 체크박스
        watched_key = f"{watched_key_prefix}_{video_id}"
        is_watched = st.checkbox(
            "✅ 시청 완료",
            value=st.session_state[watched_key_prefix].get(video_id, False),
            key=watched_key
        )
        st.session_state[watched_key_prefix][video_id] = is_watched
        st.markdown("---")
    
    # 모든 영상 시청 완료 체크
    all_watched = all(
        st.session_state[watched_key_prefix].get(video.get('video_id', f'video_{idx}'), False)
        for idx, video in enumerate(videos)
    )
    
    return all_watched

def render_book_table(books):
    """책 카드 형식으로 표시 (3권씩 가로로 한 줄)"""
    if not books:
        return
    
    # 3권씩 가로로 표시
    display_books = books[:3]
    cols = st.columns(3)
    
    for idx, (col, book) in enumerate(zip(cols, display_books)):
        with col:
            # 카드 데이터
            cover_url = book.get('cover_image_url', '')
            title = book.get('title', '제목 없음')
            author = book.get('author', '정보 없음')
            keywords = book.get('keywords', [])
            pages = book.get('pages', 0)
            
            # 카드 컨테이너 시작
            st.markdown("""
            <div style="background: white; border-radius: 12px; padding: 1.2rem; box-shadow: 0 4px 12px rgba(0,0,0,0.08); margin-bottom: 1.5rem; height: 100%; display: flex; flex-direction: column;">
            """, unsafe_allow_html=True)
            
            # 책표지 이미지
            if cover_url:
                st.image(cover_url, use_container_width=True)
            else:
                st.image("https://via.placeholder.com/200x300/667eea/ffffff?text=📚", use_container_width=True)
            
            # 제목
            st.markdown(f"**{title}**")
            
            # 저자
            st.markdown(f"👤 {author}")
            
            # 페이지 수
            if pages:
                st.markdown(f"📄 {pages}페이지")
            
            # 키워드 태그
            if keywords:
                keyword_tags = []
                for kw in keywords[:3]:
                    if kw and kw.strip():
                        keyword_tags.append(kw.strip())
                
                if keyword_tags:
                    # 키워드를 태그 형식으로 표시
                    tags_html = ""
                    for kw in keyword_tags:
                        tags_html += f'<span style="background: #667eea; color: white; padding: 0.3rem 0.6rem; border-radius: 12px; font-size: 0.75rem; margin: 0.2rem 0.2rem 0.2rem 0; display: inline-block;">{kw}</span>'
                    
                    st.markdown(f"""
                    <div style="margin-top: 0.8rem;">
                        <div style="display: flex; flex-wrap: wrap; gap: 0.3rem;">
                            {tags_html}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            
            # 카드 컨테이너 종료
            st.markdown("</div>", unsafe_allow_html=True)

def render_escape_card(video, index):
    """탈출 콘텐츠 카드 렌더링"""
    video_id = video.get('video_id', '')
    channel = video.get('channel', '')
    embed_url = f"https://www.youtube.com/embed/{video_id}" if video_id else ""
    
    st.markdown(f"""
    <div class="escape-card">
        <h3>🚀 {video.get('title', '제목 없음')}</h3>
        {f'<p><strong>📺 채널:</strong> {channel}</p>' if channel else ''}
        <p><strong>🏷️ 카테고리:</strong> {video.get('category', '기타')}</p>
        <p><strong>📊 조회수:</strong> {video.get('views', '정보 없음')} | <strong>⏱️ 길이:</strong> {video.get('duration', '정보 없음')}</p>
        <p><strong>📝 요약:</strong> {video.get('summary', '요약 없음')}</p>
        <p><strong>💡 왜 도움이 될까요?</strong> {video.get('reason', '')}</p>
        <a href="{video.get('url', '#')}" target="_blank" style="color: white; text-decoration: underline; font-weight: bold;">🔗 YouTube에서 보기</a>
    </div>
    """, unsafe_allow_html=True)
    
    # YouTube 영상 임베드
    if video_id:
        st.markdown(f"""
        <div style="margin: 1rem 0;">
            <iframe width="100%" height="400" src="{embed_url}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
        </div>
        """, unsafe_allow_html=True)

# 메인 앱
def main():
    # 대제목과 소제목
    st.markdown("""
    <div style="text-align: center; padding: 3.5rem 1rem; background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%); border-radius: 25px; margin-bottom: 2rem; box-shadow: 0 10px 40px rgba(102, 126, 234, 0.3); position: relative; overflow: hidden;">
        <div style="position: absolute; top: -50px; right: -50px; width: 200px; height: 200px; background: rgba(255, 255, 255, 0.1); border-radius: 50%;"></div>
        <div style="position: absolute; bottom: -30px; left: -30px; width: 150px; height: 150px; background: rgba(255, 255, 255, 0.08); border-radius: 50%;"></div>
        <h1 style="color: white; font-size: 3.2rem; font-weight: bold; margin-bottom: 1.2rem; text-shadow: 3px 3px 6px rgba(0,0,0,0.3); position: relative; z-index: 1;">
            퇴근후 갓생 살기 도전! 🚀
        </h1>
        <p style="color: white; font-size: 1.4rem; line-height: 1.8; opacity: 0.98; margin: 0; font-weight: 500; position: relative; z-index: 1;">
            Youtube 알고리즘을 탈출해, 퇴근후 시간 절반을 공부에 투자해보는 거 어때요?
        </p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("---")
    
    # 사이드바에 API 키 입력
    with st.sidebar:
        st.header("⚙️ 설정")
        api_key_input = st.text_input(
            "OpenAI API 키 (필수)",
            type="password",
            help="환경변수에 설정되어 있지 않은 경우 여기에 입력하세요"
        )
        if api_key_input:
            os.environ["OPENAI_API_KEY"] = api_key_input
        
        youtube_api_key_input = st.text_input(
            "YouTube API 키 (필수)",
            type="password",
            help="Google Cloud Console에서 발급받은 YouTube Data API v3 키를 입력하세요"
        )
        if youtube_api_key_input:
            st.session_state.youtube_api_key = youtube_api_key_input
            os.environ["YOUTUBE_API_KEY"] = youtube_api_key_input
        
        st.markdown("---")
        st.info("💡 YouTube API 키를 입력하면 빠르고 안정적으로 YouTube 영상을 검색할 수 있습니다.")
    
    # 1. 적정 유튜브 & 독서 시간 추천 화면
    st.markdown("### ⏰ 나의 일일 시간 배분")
    
    # 애니메이션 CSS 추가
    st.markdown("""
    <style>
    @keyframes personWalk {
        0% { transform: translateX(0) translateY(0); }
        25% { transform: translateX(25px) translateY(-5px); }
        50% { transform: translateX(50px) translateY(0); }
        75% { transform: translateX(75px) translateY(-5px); }
        100% { transform: translateX(100px) translateY(0); }
    }
    
    @keyframes moonRise {
        0% { transform: translateY(20px); opacity: 0; }
        100% { transform: translateY(0); opacity: 1; }
    }
    
    @keyframes zzzFloat {
        0%, 100% { transform: translateY(0) rotate(-5deg); opacity: 0.8; }
        50% { transform: translateY(-10px) rotate(5deg); opacity: 1; }
    }
    
    @keyframes clockSplit {
        0% { transform: scale(1); }
        50% { transform: scale(1.1); }
        100% { transform: scale(1); }
    }
    
    @keyframes highlightPulse {
        0%, 100% { box-shadow: 0 0 0 0 rgba(102, 126, 234, 0.7); }
        50% { box-shadow: 0 0 20px 10px rgba(102, 126, 234, 0.7); }
    }
    
    @keyframes bubbleFloat {
        0%, 100% { transform: translateY(0); opacity: 0.8; }
        50% { transform: translateY(-5px); opacity: 1; }
    }
    
    .work-animation {
        width: 100%;
        height: 80px;
        position: relative;
        margin-bottom: 1rem;
    }
    
    .building {
        position: absolute;
        left: 10px;
        bottom: 0;
        font-size: 2rem;
    }
    
    .person {
        position: absolute;
        left: 10px;
        bottom: 10px;
        font-size: 1.5rem;
        animation: personWalk 2s ease-in-out infinite;
    }
    
    .house {
        position: absolute;
        right: 10px;
        bottom: 0;
        font-size: 2rem;
    }
    
    .sleep-animation {
        width: 100%;
        height: 80px;
        position: relative;
        margin-bottom: 1rem;
    }
    
    .moon {
        position: absolute;
        top: 10px;
        right: 20px;
        font-size: 2rem;
        animation: moonRise 1.5s ease-out;
    }
    
    .sleep-house {
        position: absolute;
        left: 50%;
        transform: translateX(-50%);
        bottom: 0;
        font-size: 2rem;
    }
    
    .zzz {
        position: absolute;
        left: 50%;
        transform: translateX(-50%);
        bottom: 30px;
        font-size: 1.2rem;
        font-weight: bold;
        color: #667eea;
        animation: zzzFloat 1.5s ease-in-out infinite;
    }
    
    .clock-animation {
        width: 100%;
        height: 100px;
        position: relative;
        margin-bottom: 1rem;
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 2rem;
    }
    
    .clock-container {
        position: relative;
        animation: clockSplit 1s ease-in-out;
    }
    
    .clock-highlight {
        font-size: 3rem;
        animation: highlightPulse 2s ease-in-out infinite;
        border-radius: 50%;
        padding: 0.5rem;
    }
    
    .clock-normal {
        font-size: 2.5rem;
    }
    
    .how-bubble {
        position: absolute;
        top: -30px;
        right: -20px;
        background: #667eea;
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 20px;
        font-size: 0.9rem;
        font-weight: bold;
        animation: bubbleFloat 1.5s ease-in-out infinite;
    }
    
    .how-bubble::after {
        content: '';
        position: absolute;
        bottom: -8px;
        left: 20px;
        width: 0;
        height: 0;
        border-left: 8px solid transparent;
        border-right: 8px solid transparent;
        border-top: 8px solid #667eea;
    }
    </style>
    """, unsafe_allow_html=True)
    
    time_col1, time_col2, time_col3 = st.columns([1.2, 1.2, 1.6])
    
    with time_col1:
        st.markdown("**퇴근 시간**")
        
        # 퇴근시간 입력
        work_end_time = st.time_input(
            "시계를 클릭하여 시간을 선택하세요",
            value=datetime.strptime("18:00", "%H:%M").time(),
            key="work_end_time",
            label_visibility="collapsed"
        )
        work_end_hour = work_end_time.hour
        work_end_minute = work_end_time.minute
        
        # 퇴근시간 애니메이션 (입력 칸 아래에 표시)
        if work_end_time:
            st.session_state.work_end_time_set = True
            st.markdown("""
            <div class="work-animation" style="margin-top: 1rem;">
                <div class="building">🏢</div>
                <div class="person">🚶</div>
                <div class="house">🏠</div>
            </div>
            """, unsafe_allow_html=True)
    
    with time_col2:
        st.markdown("**취침 시간**")
        
        # 취침시간 입력
        sleep_time = st.time_input(
            "시계를 클릭하여 시간을 선택하세요",
            value=datetime.strptime("23:00", "%H:%M").time(),
            key="sleep_time",
            label_visibility="collapsed"
        )
        sleep_hour = sleep_time.hour
        sleep_minute = sleep_time.minute
        
        # 취침시간 애니메이션 (입력 칸 아래에 표시)
        if sleep_time:
            st.session_state.sleep_time_set = True
            st.markdown("""
            <div class="sleep-animation" style="margin-top: 1rem;">
                <div class="moon">🌙</div>
                <div class="sleep-house">🏠</div>
                <div class="zzz">Zzzz</div>
            </div>
            """, unsafe_allow_html=True)
    
    # 시간 계산
    work_end_time_minutes = work_end_hour * 60 + work_end_minute
    sleep_time_minutes = sleep_hour * 60 + sleep_minute
    if sleep_time_minutes <= work_end_time_minutes:
        sleep_time_minutes += 24 * 60  # 다음날로
    
    available_minutes = sleep_time_minutes - work_end_time_minutes
    study_minutes = int(available_minutes * 0.5)  # 50% 배분
    youtube_minutes = int(study_minutes * 0.6)  # 유튜브 60%
    reading_minutes = int(study_minutes * 0.4)  # 독서 40%
    
    with time_col3:
        st.markdown("**시간 배분**")
        
        # 두 시간 모두 입력 시 시계 분할 애니메이션
        if work_end_time and sleep_time:
            st.markdown("""
            <div class="clock-animation" style="margin-top: 1rem;">
                <div class="clock-container">
                    <div class="clock-highlight">⏰</div>
                    <div class="how-bubble">HOW?</div>
                </div>
                <div class="clock-normal">⏰</div>
            </div>
            <p style="text-align: center; color: #666; font-size: 0.85rem; margin-top: 0.5rem;">퇴근후 시간의 절반을 배분할게요</p>
            """, unsafe_allow_html=True)
        
        # 시간 배분을 압축해서 표시
        if work_end_time and sleep_time:
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 1rem; border-radius: 12px; color: white; margin-top: 1rem; font-size: 0.9rem;">
                <p style="margin: 0.3rem 0;"><strong>잔여 시간:</strong> {available_minutes}분 ({available_minutes//60}시간 {available_minutes%60}분)</p>
                <p style="margin: 0.3rem 0;"><strong>🎥 YouTube 학습:</strong> {youtube_minutes}분 ({youtube_minutes//60}시간 {youtube_minutes%60}분)</p>
                <p style="margin: 0.3rem 0;"><strong>📚 독서 시간:</strong> {reading_minutes}분 ({reading_minutes//60}시간 {reading_minutes%60}분)</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("<div style='padding: 1rem; text-align: center; color: #666; margin-top: 1rem;'>시간을 입력하면<br>배분이 계산됩니다</div>", unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 2. 키워드 입력 화면 (클릭 선택 + 직접 입력, 카테고리별 색상)
    st.markdown("### 📝 공부하고 싶은 키워드를 선택하거나 입력하세요")
    
    # 키워드 카테고리별 그룹화 및 색상 정의 (각 카테고리별 5개로 제한, AI와 인공지능 중복 제거)
    keyword_categories = {
        "AI & 프로그래밍": {
            "keywords": ["AI", "머신러닝", "딥러닝", "데이터사이언스", "프로그래밍"],
            "color": "#4F46E5",  # 인디고
            "bg_color": "#EEF2FF"
        },
        "심리 & 자기계발": {
            "keywords": ["심리학", "인간관계", "소통", "리더십", "자기계발"],
            "color": "#DC2626",  # 레드
            "bg_color": "#FEE2E2"
        },
        "경제 & 투자": {
            "keywords": ["부동산", "국내주식", "해외주식", "부업", "투자"],
            "color": "#F59E0B",  # 앰버
            "bg_color": "#FEF3C7"
        },
        "회사생활": {
            "keywords": ["팀워크", "신입", "이직", "커리어", "업무"],
            "color": "#8B5CF6",  # 바이올렛
            "bg_color": "#EDE9FE"
        },
        "인문학": {
            "keywords": ["국제정치", "역사", "철학", "문학", "사회"],
            "color": "#7C3AED",  # 바이올렛
            "bg_color": "#EDE9FE"
        },
        "운동 & 건강": {
            "keywords": ["홈트레이닝", "런닝", "건강", "요가", "다이어트"],
            "color": "#10B981",  # 그린
            "bg_color": "#D1FAE5"
        },
        "라이프스타일": {
            "keywords": ["요리", "여행", "예술", "음악", "취미"],
            "color": "#EC4899",  # 핑크
            "bg_color": "#FCE7F3"
        }
    }
    
    # 세션 상태 초기화
    if "selected_keywords" not in st.session_state:
        st.session_state.selected_keywords = []
    if "keyword_difficulties" not in st.session_state:
        st.session_state.keyword_difficulties = {}
    
    # 카테고리별로 키워드 태그 형식으로 표시 (COMPACT, 열로 배치)
    st.markdown("**💡 키워드를 클릭하여 선택하세요**")
    
    # 카테고리를 2열로 배치
    category_list = list(keyword_categories.items())
    for i in range(0, len(category_list), 2):
        row_categories = category_list[i:i+2]
        cols = st.columns(2)
        
        for col_idx, (col, (category_name, category_info)) in enumerate(zip(cols, row_categories)):
            with col:
                # COMPACT한 카테고리 헤더
                st.markdown(f"""
                <div style="margin-bottom: 0.5rem;">
                    <span style="color: {category_info['color']}; font-weight: bold; font-size: 0.95rem;">{category_name}</span>
                </div>
                """, unsafe_allow_html=True)
                
                # 키워드 태그들을 한 줄에 모두 표시 (5개)
                keywords = category_info["keywords"][:5]  # 최대 5개만
                keyword_cols = st.columns(5)  # 5개 컬럼
                
                for k, (kw_col, keyword) in enumerate(zip(keyword_cols, keywords)):
                        with kw_col:
                            is_selected = keyword in st.session_state.selected_keywords
                            
                            # 태그 스타일 적용
                            if is_selected:
                                # 선택된 태그: 진한 색상
                                button_label = f"{keyword} ×"
                                button_type = "primary"
                                button_style = f"""
                                <style>
                                button[kind="primary"][data-testid="baseButton-primary"]:has-text("{keyword}") {{
                                    background-color: {category_info['color']} !important;
                                    color: white !important;
                                    border: none !important;
                                    border-radius: 20px !important;
                                    padding: 0.4rem 0.8rem !important;
                                    font-size: 0.85rem !important;
                                    font-weight: normal !important;
                                    box-shadow: none !important;
                                    width: 100% !important;
                                }}
                                </style>
                                """
                            else:
                                # 선택 안 된 태그: 연한 배경색
                                button_label = keyword
                                button_type = "secondary"
                                button_style = f"""
                                <style>
                                button[kind="secondary"][data-testid="baseButton-secondary"]:has-text("{keyword}") {{
                                    background-color: {category_info['bg_color']} !important;
                                    color: {category_info['color']} !important;
                                    border: 1px solid {category_info['color']} !important;
                                    border-radius: 20px !important;
                                    padding: 0.4rem 0.8rem !important;
                                    font-size: 0.85rem !important;
                                    font-weight: normal !important;
                                    box-shadow: none !important;
                                    width: 100% !important;
                                }}
                                </style>
                                """
                            
                            st.markdown(button_style, unsafe_allow_html=True)
                            
                            if st.button(button_label, key=f"kw_btn_{keyword}", use_container_width=True, type=button_type):
                                # 키워드 토글
                                if keyword in st.session_state.selected_keywords:
                                    st.session_state.selected_keywords.remove(keyword)
                                    if keyword in st.session_state.keyword_difficulties:
                                        del st.session_state.keyword_difficulties[keyword]
                                else:
                                    st.session_state.selected_keywords.append(keyword)
                                    # 기본 난이도 설정
                                    if keyword not in st.session_state.keyword_difficulties:
                                        st.session_state.keyword_difficulties[keyword] = 1  # 0: 입문, 1: 중급, 2: 고급
                                st.rerun()
        
        # 카테고리 간 간격
        if i + 2 < len(category_list):
            st.markdown("<br>", unsafe_allow_html=True)
    
    # 직접 입력 (카테고리 섹션 밖으로 분리)
    st.markdown("---")
    st.markdown("**✏️ 또는 직접 입력하세요**")
    custom_keyword = st.text_input(
        "키워드 직접 입력",
        placeholder="예: 블록체인, 미술사 등",
        key="custom_keyword_input"
    )
    
    if custom_keyword and custom_keyword.strip():
        if st.button("➕ 추가", key="add_custom_keyword"):
            keyword = custom_keyword.strip()
            if keyword not in st.session_state.selected_keywords:
                st.session_state.selected_keywords.append(keyword)
                st.session_state.keyword_difficulties[keyword] = 1  # 기본 난이도: 중급
                st.rerun()
    
    # 선택된 키워드와 난이도 설정
    st.markdown("---")
    st.markdown("**🎯 선택된 키워드 및 나의 지식 수준 설정**")
    
    if st.session_state.selected_keywords:
        for idx, keyword in enumerate(st.session_state.selected_keywords):
            # 키워드가 속한 카테고리 찾기
            keyword_category = None
            for cat_name, cat_info in keyword_categories.items():
                if keyword in cat_info["keywords"]:
                    keyword_category = cat_info
                    break
            
            # 카테고리 색상이 없으면 기본 색상 사용
            if not keyword_category:
                keyword_category = {"color": "#667eea", "bg_color": "#EEF2FF"}
            
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                # 태그 형식으로 키워드 표시
                st.markdown(f"""
                <div style="display: inline-flex; align-items: center; gap: 0.5rem;">
                    <span style="background-color: {keyword_category['color']}; color: white; padding: 0.5rem 1rem; border-radius: 20px; font-size: 0.9rem; font-weight: bold;">
                        {keyword}
                    </span>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                # 나의 지식 수준 슬라이더
                difficulty_labels = ["입문", "중급", "고급"]
                current_difficulty = st.session_state.keyword_difficulties.get(keyword, 1)
                difficulty = st.slider(
                    f"나의 지식 수준: {difficulty_labels[current_difficulty]}",
                    min_value=0,
                    max_value=2,
                    value=current_difficulty,
                    key=f"difficulty_{keyword}",
                    help="0: 입문, 1: 중급, 2: 고급"
                )
                st.session_state.keyword_difficulties[keyword] = difficulty
            with col3:
                # 삭제 버튼 (작고 깔끔하게)
                if st.button("✕", key=f"remove_{keyword}", use_container_width=False, help="삭제"):
                    st.session_state.selected_keywords.remove(keyword)
                    if keyword in st.session_state.keyword_difficulties:
                        del st.session_state.keyword_difficulties[keyword]
                    st.rerun()
    else:
        st.info("💡 위의 키워드를 클릭하거나 직접 입력하여 키워드를 추가하세요.")
    
    # 추천 받기 버튼
    st.markdown("<br>", unsafe_allow_html=True)
    col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
    with col_btn2:
        recommend_button = st.button("✨ 추천 받기", use_container_width=True, type="primary")
    
    # 세션 상태 초기화
    if "youtube_recommendations" not in st.session_state:
        st.session_state.youtube_recommendations = []
    if "book_recommendations" not in st.session_state:
        st.session_state.book_recommendations = []
    if "escape_recommendations" not in st.session_state:
        st.session_state.escape_recommendations = []
    if "nickname" not in st.session_state:
        st.session_state.nickname = "성장하는 학습자"
    
    # 추천 생성
    if recommend_button:
        # 선택된 키워드 가져오기
        keywords = st.session_state.selected_keywords.copy()
        
        if not keywords:
            st.warning("⚠️ 최소 1개 이상의 키워드를 선택하거나 입력해주세요!")
        else:
            # 키워드별 난이도 정보 가져오기
            keyword_difficulties = st.session_state.keyword_difficulties.copy()
            # OpenAI 클라이언트 초기화
            try:
                client = init_openai_client()
            except:
                st.error("OpenAI API 키를 설정해주세요.")
                st.stop()
            
            # YouTube API 클라이언트 초기화
            youtube_client = init_youtube_client()
            if not youtube_client:
                st.error("⚠️ YouTube API 키가 필요합니다. 사이드바에서 입력해주세요.")
                st.info("💡 YouTube API 키 발급 방법:\n1. [Google Cloud Console](https://console.cloud.google.com/) 접속\n2. 프로젝트 생성 후 'API 및 서비스' > '라이브러리'\n3. 'YouTube Data API v3' 활성화\n4. '사용자 인증 정보'에서 API 키 생성")
                st.stop()
            
            # 별명 생성
            with st.spinner("🌟 멋진 별명을 생성하고 있어요..."):
                nickname = generate_nickname(client, keywords)
                st.session_state.nickname = nickname
            
            # 로딩 표시
            with st.spinner("🎬 맞춤 영상을 찾고 있어요..."):
                youtube_recs = generate_youtube_recommendations(client, youtube_client, keywords, keyword_difficulties)
                st.session_state.youtube_recommendations = youtube_recs
                
                # 디버깅: 영상이 없을 때 메시지 표시
                if not youtube_recs or len(youtube_recs) == 0:
                    st.error("⚠️ YouTube 영상 추천에 실패했습니다. 다음을 확인해주세요:")
                    st.info("""
                    1. YouTube API 키가 올바르게 설정되었는지 확인
                    2. API 할당량이 남아있는지 확인
                    3. 다른 키워드로 시도해보세요
                    4. 네트워크 연결을 확인해주세요
                    """)
            
            with st.spinner("📚 최고의 책을 선별하고 있어요..."):
                book_recs = generate_book_recommendations(client, keywords)
                st.session_state.book_recommendations = book_recs
            
            with st.spinner("🚀 알고리즘 탈출 콘텐츠를 준비하고 있어요..."):
                escape_recs = generate_escape_recommendations(client, youtube_client, keywords)
                st.session_state.escape_recommendations = escape_recs
            
            st.success("✅ 추천이 완료되었습니다!")
            st.balloons()
            # 축하 메시지 플래그 리셋 (새로운 추천이므로)
            st.session_state.celebration_shown = False
            st.rerun()  # 별명 업데이트를 위해 페이지 새로고침
    
    # 결과 표시
    all_youtube_watched = False
    all_escape_watched = False
    
    # YouTube 추천 영상 표시
    if st.session_state.youtube_recommendations and len(st.session_state.youtube_recommendations) > 0:
        st.markdown("---")
        st.markdown("<h2>🎥 키워드 기반 맞춤 YouTube 영상 (5분~30분)</h2>", unsafe_allow_html=True)
        st.markdown("<p style='color: #64748b; margin-bottom: 1.5rem;'>💡 맞춤영상을 시청 완료하였으면 <strong>체크</strong> 해주세요.</p>", unsafe_allow_html=True)
        
        # 키워드별로 영상 분류 (선택된 키워드 순서대로)
        keywords_list = st.session_state.selected_keywords.copy()
        if not keywords_list:
            keywords_list = ["일반"]
        
        # 키워드별로 영상 그룹화 (선택된 키워드 순서 유지)
        videos_by_keyword = {}
        for keyword in keywords_list:
            videos_by_keyword[keyword] = []
        
        for video in st.session_state.youtube_recommendations:
            keyword = video.get('keyword', keywords_list[0] if keywords_list else "일반")
            if keyword in videos_by_keyword:
                videos_by_keyword[keyword].append(video)
        
        # 키워드 개수에 따라 레이아웃 결정
        num_keywords = len([k for k in keywords_list if k in videos_by_keyword and len(videos_by_keyword[k]) > 0])
        
        # 디버깅: 영상이 있는지 확인
        if num_keywords == 0:
            # 키워드가 없어도 영상이 있으면 표시
            if len(st.session_state.youtube_recommendations) > 0:
                # 키워드 정보가 없는 영상들을 "일반"으로 분류
                videos_by_keyword["일반"] = st.session_state.youtube_recommendations
                keywords_list = ["일반"]
                num_keywords = 1
        
        if num_keywords > 0:
            if num_keywords == 1:
                # 키워드 1개: 3*2 레이아웃 (두 줄)
                keyword = keywords_list[0]
                videos = videos_by_keyword.get(keyword, [])[:6]  # 최대 6개
                st.markdown(f"### {keyword}")
                
                # 첫 번째 줄: 3개
                row1_cols = st.columns(3)
                for idx, video in enumerate(videos[:3]):
                    with row1_cols[idx]:
                        render_single_video(video, watched_key_prefix="youtube_watched")
                
                # 두 번째 줄: 3개
                if len(videos) > 3:
                    row2_cols = st.columns(3)
                    for idx, video in enumerate(videos[3:6]):
                        with row2_cols[idx]:
                            render_single_video(video, watched_key_prefix="youtube_watched")
            
            elif num_keywords == 2:
                # 키워드 2개: 2*3 레이아웃 (키워드별 세로 배치)
                cols = st.columns(2)
                for idx, keyword in enumerate(keywords_list[:2]):
                    if keyword in videos_by_keyword and len(videos_by_keyword[keyword]) > 0:
                        videos = videos_by_keyword[keyword][:3]  # 최대 3개
                        with cols[idx]:
                            st.markdown(f"### {keyword}")
                            render_youtube_table(
                                videos,
                                watched_key_prefix="youtube_watched"
                            )
            
            else:  # 3개 이상
                # 키워드 3개: 3*2 레이아웃 (키워드별 가로 배치)
                # 먼저 키워드 헤더 표시
                header_cols = st.columns(3)
                for idx, keyword in enumerate(keywords_list[:3]):
                    if keyword in videos_by_keyword and len(videos_by_keyword[keyword]) > 0:
                        with header_cols[idx]:
                            st.markdown(f"### {keyword}")
                
                # 영상 표시 (가로로, 각 키워드별로 2개씩)
                for row_idx in range(2):  # 최대 2줄
                    row_cols = st.columns(3)
                    for col_idx, keyword in enumerate(keywords_list[:3]):
                        if keyword in videos_by_keyword and len(videos_by_keyword[keyword]) > row_idx:
                            videos = videos_by_keyword[keyword]
                            if row_idx < len(videos):
                                with row_cols[col_idx]:
                                    render_single_video(videos[row_idx], watched_key_prefix="youtube_watched")
        
        # 전체 시청 완료 체크
        if "youtube_watched" not in st.session_state:
            st.session_state["youtube_watched"] = {}
        all_youtube_watched = all(
            st.session_state["youtube_watched"].get(video.get('video_id', ''), False)
            for video in st.session_state.youtube_recommendations
        )
    
    if st.session_state.book_recommendations:
        st.markdown("---")
        st.markdown("<h2>📚 추천 도서</h2>", unsafe_allow_html=True)
        
        # 모든 도서를 한 번에 표시 (3권씩 가로로)
        render_book_table(st.session_state.book_recommendations)
    
    if st.session_state.escape_recommendations:
        st.markdown("---")
        st.markdown("<h2>🚀 알고리즘 탈출용 이색 콘텐츠</h2>", unsafe_allow_html=True)
        st.markdown("<p style='color: #64748b;'>💡 완전히 다른 영역의 콘텐츠로 사고를 확장해보세요!</p>", unsafe_allow_html=True)
        
        all_escape_watched = render_youtube_table(
            st.session_state.escape_recommendations,
            watched_key_prefix="escape_watched"
        )
    
    # 키워드 기반 맞춤 유튜브만 시청 완료 축하 메시지 (알고리즘 탈출용은 제외)
    if st.session_state.youtube_recommendations:
        if all_youtube_watched:
            # 축하 메시지 표시 (한 번만)
            if "celebration_shown" not in st.session_state or not st.session_state.celebration_shown:
                st.markdown("---")
                st.markdown("""
                <div style="text-align: center; padding: 3rem; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 20px; color: white; margin: 2rem 0;">
                    <h1 style="font-size: 3rem; margin-bottom: 1rem;">🎉</h1>
                    <h2 style="font-size: 2rem; margin-bottom: 1rem;">오늘도 갓생 한걸음!</h2>
                    <p style="font-size: 1.5rem;">모든 추천 영상을 시청하셨네요! 정말 멋져요! 🚀</p>
                </div>
                """, unsafe_allow_html=True)
                st.balloons()
                st.session_state.celebration_shown = True
            else:
                st.markdown("---")
                st.markdown("""
                <div style="text-align: center; padding: 2rem; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 20px; color: white; margin: 2rem 0;">
                    <h2 style="font-size: 1.8rem;">🎉 오늘도 갓생 한걸음!</h2>
                    <p style="font-size: 1.2rem;">모든 추천 영상을 시청하셨습니다! 🚀</p>
                </div>
                """, unsafe_allow_html=True)
        else:
            # 아직 완료하지 않았으면 축하 메시지 플래그 리셋
            st.session_state.celebration_shown = False
    
    # 어제의 스몸비와 오늘의 나 비교 화면 (맨 아래)
    st.markdown("---")
    st.markdown("### 🌟 어제의 스몸비 vs 오늘의 나")
    
    comparison_col1, comparison_col2 = st.columns(2)
    
    with comparison_col1:
        st.markdown("""
        <div style="text-align: center; padding: 2rem; background: #f0f0f0; border-radius: 15px;">
            <h2>😴 어제의 스몸비</h2>
            <p style="font-size: 5rem;">😔</p>
            <p style="font-size: 1.2rem; color: #666;">스몸비 모드</p>
            <p style="font-size: 1.2rem; color: #666;">힘들어하고 지친 모습</p>
        </div>
        """, unsafe_allow_html=True)
    
    with comparison_col2:
        nickname = st.session_state.get('nickname', '오늘의 나는 성장하는 학습자')
        # 키워드가 있으면 별명 표시, 없으면 기본 문구
        if st.session_state.selected_keywords:
            display_text = nickname
        else:
            display_text = "오늘의 나는 성장하는 학습자"
        
        st.markdown(f"""
        <div style="text-align: center; padding: 2rem; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 15px; color: white;">
            <h2>✨ {display_text}</h2>
            <p style="font-size: 5rem;">🚀</p>
            <p style="font-size: 1.3rem; font-weight: bold; line-height: 1.6;">{display_text}</p>
            <p style="font-size: 1.1rem; margin-top: 1rem;">당당하고 멋진 전문가</p>
        </div>
        """, unsafe_allow_html=True)
    
    # 푸터
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #94a3b8; padding: 2rem;'>"
        "🎈 알고리즘에 갇히지 말고, 다양한 콘텐츠로 지적 호기심을 키워보세요!"
        "</div>",
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()

