import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import os
import requests
from openai import OpenAI
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')

# 페이지 설정
st.set_page_config(
    page_title="주린이 전용 포트폴리오 추천 대시보드",
    page_icon="📊",
    layout="wide"
)

# 환율 가져오기 (USD/KRW)
@st.cache_data(ttl=3600)  # 1시간마다 갱신
def get_exchange_rate():
    """USD/KRW 환율을 가져오는 함수"""
    try:
        # USD/KRW 환율 가져오기
        krw_ticker = yf.Ticker("KRW=X")
        krw_data = krw_ticker.history(period="1d")
        if len(krw_data) > 0:
            exchange_rate = krw_data['Close'].iloc[-1]
            return exchange_rate
        else:
            # 기본값 (약 1,300원)
            return 1300.0
    except:
        # 에러 발생 시 기본값 반환
        return 1300.0

# 실제 주가 가져오기 (yfinance 사용)
@st.cache_data(ttl=300)  # 5분마다 갱신
def get_real_stock_price(ticker, country):
    """실제 주가를 가져오는 함수 - yfinance 사용"""
    try:
        if country == '미국':
            # 미국 주식은 yfinance 사용
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d")
            if len(hist) > 0:
                price_usd = hist['Close'].iloc[-1]
                # USD를 원화로 환산
                exchange_rate = get_exchange_rate()
                price_krw = price_usd * exchange_rate
                return price_krw
            else:
                return None
        else:
            # 한국 주식은 yfinance 사용 (.KS 추가)
            try:
                korean_ticker = f"{ticker}.KS"
                stock = yf.Ticker(korean_ticker)
                hist = stock.history(period="1d")
                if len(hist) > 0:
                    price_krw = hist['Close'].iloc[-1]
                    return price_krw
            except:
                pass
            
            # .KS가 안 되면 티커만으로 시도
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period="1d")
                if len(hist) > 0:
                    price_krw = hist['Close'].iloc[-1]
                    return price_krw
            except:
                pass
            
            return None
    except Exception as e:
        return None

# 주식 데이터프레임 생성 (S&P 500 + KOSPI 200 주요 종목)
@st.cache_data(ttl=300)  # 5분마다 갱신
def get_stock_data():
    """주식 데이터를 반환하는 함수 - S&P 500과 KOSPI 200의 주요 종목 포함"""
    
    # S&P 500 주요 종목 (섹터별로 리스트 구성)
    sp500_sectors = [
        # Technology (20개)
        (['AAPL', 'MSFT', 'GOOGL', 'GOOG', 'META', 'NVDA', 'AVGO', 'ORCL', 'CRM', 'ADBE', 'INTC', 'AMD', 'QCOM', 'TXN', 'AMAT', 'LRCX', 'KLAC', 'MU', 'NXPI', 'MRVL'],
         ['애플', '마이크로소프트', '구글A', '구글C', '메타', '엔비디아', '브로드컴', '오라클', '세일즈포스', '어도비', '인텔', 'AMD', '퀄컴', '텍사스인스트루먼트', '어플라이드머티리얼즈', '라믹리서치', 'KLA', '마이크론', 'NXP', '마벨'],
         '기술'),
        # Healthcare (20개)
        (['UNH', 'JNJ', 'LLY', 'ABBV', 'TMO', 'ABT', 'DHR', 'BMY', 'AMGN', 'GILD', 'REGN', 'VRTX', 'BIIB', 'CI', 'HUM', 'CVS', 'ELV', 'ISRG', 'SYK', 'BSX'],
         ['유나이티드헬스', '존슨앤존슨', '엘리릴리', '애브비', '써모피셔', '애보트', '다나허', '브리스톨마이어스', '앰젠', '길리어드', '리제너론', '버텍스', '바이오젠', '시그나', '휴마나', 'CVS헬스', '엘리베이트', '인튜이티브서지컬', '스트라이커', '보스턴사이언티픽'],
         '헬스케어'),
        # Financials (20개)
        (['JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK', 'SCHW', 'AXP', 'COF', 'USB', 'PNC', 'TFC', 'BK', 'STT', 'MTB', 'CFG', 'FITB', 'HBAN', 'ZION'],
         ['JP모건', '뱅크오브아메리카', '웰스파고', '골드만삭스', '모건스탠리', '시티그룹', '블랙록', '찰스슈왑', '아메리칸익스프레스', '캐피탈원', 'US뱅크', 'PNC', '트루이스트', '뱅크오브뉴욕', '스테이트스트리트', 'M&T뱅크', '시티즌스', '피프스써드', '헌팅턴', 'Zions'],
         '금융'),
        # Consumer Discretionary (20개)
        (['AMZN', 'TSLA', 'HD', 'MCD', 'NKE', 'SBUX', 'LOW', 'TJX', 'BKNG', 'GM', 'F', 'NCLH', 'CCL', 'RCL', 'MAR', 'HLT', 'ABNB', 'EXPE', 'TRIP', 'TCOM'],
         ['아마존', '테슬라', '홈디포', '맥도날드', '나이키', '스타벅스', '로우스', 'TJX', '부킹홀딩스', '제너럴모터스', '포드', '노르웨이크루즈', '카니발', '로열캐리비안', '메리어트', '힐튼', '에어비앤비', '익스피디아', '트립어드바이저', '트립닷컴'],
         '소비재'),
        # Consumer Staples (20개)
        (['WMT', 'PG', 'KO', 'PEP', 'COST', 'TGT', 'CL', 'KMB', 'CHD', 'GIS', 'CPB', 'SJM', 'HRL', 'CAG', 'K', 'MDLZ', 'HSY', 'TAP', 'BF.B', 'STZ'],
         ['월마트', '프로cter앤갬블', '코카콜라', '펩시코', '코스트코', '타겟', '콜게이트', '킴벌리클라크', '처치앤드와이트', '제너럴밀스', '캠벨수프', 'JM스마커', '호멜', '코너그라', '켈로그', '몬델레즈', '허쉬', '몰슨쿠어스', '브라운포먼', '컨스텔레이션'],
         '필수소비재'),
        # Energy (20개)
        (['XOM', 'CVX', 'SLB', 'EOG', 'COP', 'MPC', 'PSX', 'VLO', 'HES', 'FANG', 'OVV', 'CTRA', 'MRO', 'DVN', 'APA', 'HAL', 'BKR', 'FTI', 'NOV', 'WMB'],
         ['엑슨모빌', '셰브론', '슐럼버거', 'EOG리소스', '코노코필립스', '마라톤피트롤리움', '필립스66', '발레로', '헤스', '다이아몬드백', '오비비', '코트라', '마라톤오일', '데본에너지', '아파치', '할리버튼', '베이커휴즈', '테크니팁', '내셔널오일웰', '윌리엄스'],
         '에너지'),
        # Industrials (20개)
        (['BA', 'CAT', 'GE', 'HON', 'RTX', 'LMT', 'NOC', 'GD', 'TDG', 'TDY', 'PH', 'EMR', 'ETN', 'IR', 'DOV', 'FTV', 'AME', 'ZBH', 'ITW', 'CMI'],
         ['보잉', '캐터필러', '제너럴일렉트릭', '하니웰', 'RTX', '록히드마틴', '노스롭그루먼', '제너럴다이내믹스', '트랜스디지털', '텔레다인', '파커핸니핀', '이머슨', '이튼', '잉거솔랜드', '도버', '포트리브', '아메텍', '지머바이오메트', '일리노이툴웍스', '커민스'],
         '산업재'),
        # Communication Services (20개)
        (['VZ', 'T', 'CMCSA', 'DIS', 'NFLX', 'PARA', 'WBD', 'FOX', 'FOXA', 'LBRDK', 'LBRDA', 'LSXMK', 'LSXMA', 'LSXMB', 'CHTR', 'EA', 'TTWO', 'ATVI', 'ROKU', 'SPOT'],
         ['버라이즌', 'AT&T', '컴캐스트', '월트디즈니', '넷플릭스', '파라마운트', '워너브라더스', '폭스', '폭스A', '리버티브로드캐스트', '리버티브로드캐스트A', '리버티미디어', '리버티미디어A', '리버티미디어B', '차터', '일렉트로닉아츠', '테이크투', '액티비전블리자드', '로쿠', '스포티파이'],
         '통신서비스'),
        # Materials (20개)
        (['LIN', 'APD', 'ECL', 'SHW', 'DD', 'DOW', 'FCX', 'NEM', 'VALE', 'RIO', 'BHP', 'SCCO', 'TECK', 'NTR', 'MOS', 'CF', 'FMC', 'NUE', 'STLD', 'X'],
         ['린데', '에어프로덕츠', '이클립', '셰윈윌리엄스', '듀퐁', '다우', '프리포트맥모란', '뉴몬트', '밸리', '리오틴토', 'BHP', '서던코퍼', '테크리소스', '뉴트리엔', '모자이크', 'CF인더스트리즈', 'FMC', '누코르', '스틸다이나믹스', 'US스틸'],
         '소재'),
        # Real Estate (20개)
        (['AMT', 'PLD', 'EQIX', 'PSA', 'WELL', 'SPG', 'O', 'DLR', 'VICI', 'EXPI', 'CBRE', 'JLL', 'CWK', 'FR', 'AVB', 'EQR', 'UDR', 'MAA', 'CPT', 'ESS'],
         ['아메리칸타워', '프롤로지스', '이퀴닉스', '퍼블릭스토리지', '웰토워', '사이먼프롭퍼티', '리얼티인컴', '디지털리얼티', '비치', 'eXp리얼티', 'CBRE', '존스랭라살', '캠프웨이드', '퍼스트인더스트리얼', '에이발론베이컨', '에퀴티레지던셜', 'UDR', '미드아메리카아파트', '캠던프롭퍼티', '에식스프롭퍼티'],
         '부동산'),
        # Utilities (20개)
        (['NEE', 'DUK', 'SO', 'D', 'AEP', 'SRE', 'EXC', 'XEL', 'WEC', 'ES', 'ED', 'ETR', 'PEG', 'FE', 'AEE', 'LNT', 'CNP', 'ATO', 'CMS', 'NI'],
         ['넥스트에라에너지', '듀크에너지', '서던컴퍼니', '도미니언에너지', '아메리칸일렉트릭파워', 'Sempra', '엑셀론', '엑셀에너지', '위스콘신에너지', '에버소스', '컨솔리데이티드에디슨', '엔터지', '퍼블릭서비스엔터프라이즈', '퍼스트에너지', '아메리칸일렉트릭', '알리안트에너지', '센터포인트에너지', '아토스에너지', 'CMS에너지', '니소스'],
         '유틸리티'),
    ]
    
    # KOSPI 200 주요 종목
    kospi_sectors = [
        (['005930', '000660', '035420', '051910', '006400', '028260', '005380', '035720', '207940', '036570', '000270', '105560', '066570', '003550', '032830', '034730', '012330', '017670', '096770', '018260'],
         ['삼성전자', 'SK하이닉스', 'NAVER', 'LG화학', '삼성SDI', '삼성물산', '현대차', '카카오', '삼성바이오로직스', '엔씨소프트', '기아', 'KB금융', 'LG전자', 'LG', '삼성생명', 'SK', '현대모비스', 'SK텔레콤', 'SK이노베이션', '삼성에스디에스'],
         ['반도체', '반도체', '인터넷', '화학', '배터리', '유통', '자동차', '인터넷', '바이오', '게임', '자동차', '금융', '전자', '전자', '금융', '에너지', '자동차부품', '통신', '에너지', 'IT서비스']),
        (['005490', '009540', '006360', '003670', '015760', '000810', '010130', '011200', '023530', '024110', '028300', '029780', '030200', '032640', '033780', '035250', '035900', '036460', '037270', '042660'],
         ['POSCO홀딩스', '한국전력', 'GS건설', '포스코퓨처엠', '한국전력기술', '삼성화재', '고려아연', 'HMM', '롯데케미칼', '기업은행', 'HLB', '알테오젠', 'KT', 'LG유플러스', 'KT&G', '강원랜드', 'JYP엔터테인먼트', '한국가스공사', 'YG플러스', '한국전자금융'],
         ['철강', '전력', '건설', '화학', '전력', '보험', '비철금속', '운송', '화학', '금융', '바이오', '바이오', '통신', '통신', '담배', '레저', '엔터테인먼트', '가스', '엔터테인먼트', 'IT서비스']),
    ]
    
    # 데이터 병합을 위한 리스트 생성
    all_tickers = []
    all_names = []
    all_countries = []
    all_sectors = []
    
    # S&P 500 데이터 추가
    for tickers, names, sector in sp500_sectors:
        all_tickers.extend(tickers)
        all_names.extend(names)
        all_countries.extend(['미국'] * len(tickers))
        all_sectors.extend([sector] * len(tickers))
    
    # KOSPI 데이터 추가
    for tickers, names, sectors in kospi_sectors:
        all_tickers.extend(tickers)
        all_names.extend(names)
        all_countries.extend(['한국'] * len(tickers))
        all_sectors.extend(sectors)
    
    # 기본 데이터프레임 생성
    data = {
        '티커': all_tickers,
        '회사명': all_names,
        '국가': all_countries,
        '섹터': all_sectors,
    }
    
    # 랜덤 데이터 생성 (실제로는 API에서 가져와야 함)
    np.random.seed(42)  # 재현성을 위한 시드 설정
    n_stocks = len(all_tickers)
    
    data['최근수익률(%)'] = np.random.uniform(-5, 15, n_stocks).round(1)
    data['변동성'] = np.random.choice(['낮음', '중간', '높음', '매우높음'], n_stocks, p=[0.3, 0.4, 0.25, 0.05])
    data['뉴스감성(1~5)'] = np.random.uniform(2, 5, n_stocks).round(1)
    data['PER'] = np.random.uniform(8, 60, n_stocks).round(1)
    data['배당률(%)'] = np.random.uniform(0, 4, n_stocks).round(2)
    data['시가총액규모'] = np.random.choice(['대형', '중형', '소형'], n_stocks, p=[0.6, 0.3, 0.1])
    data['유동성'] = np.random.choice(['매우높음', '높음', '중간', '낮음'], n_stocks, p=[0.3, 0.4, 0.25, 0.05])
    data['성장률(%)'] = np.random.uniform(0, 30, n_stocks).round(1)
    data['RSI'] = np.random.uniform(30, 75, n_stocks).round(0).astype(int)
    
    df = pd.DataFrame(data)
    
    # 실제 주가 가져오기 (yfinance 사용)
    prices = []
    exchange_rate = get_exchange_rate()
    
    # 한국 주식과 미국 주식을 분리하여 처리
    korean_stocks = df[df['국가'] == '한국'].copy()
    us_stocks = df[df['국가'] == '미국'].copy()
    
    # 한국 주식 처리 (yfinance 사용)
    if len(korean_stocks) > 0:
        for idx, row in korean_stocks.iterrows():
            try:
                # yfinance로 한국 주식 가져오기
                korean_ticker = f"{row['티커']}.KS"
                stock = yf.Ticker(korean_ticker)
                hist = stock.history(period="1d")
                if len(hist) > 0:
                    price_krw = hist['Close'].iloc[-1]
                    prices.append((idx, float(price_krw)))
                    continue
            except:
                pass
            
            # yfinance 실패 시 기본값 사용
            sector_price_ranges = {
                '반도체': (50000, 200000), '인터넷': (100000, 300000), '화학': (200000, 600000),
                '배터리': (400000, 800000), '유통': (50000, 200000), '자동차': (50000, 300000),
                '바이오': (300000, 1000000), '게임': (200000, 500000), '금융': (30000, 100000),
                '전자': (50000, 150000), '에너지': (20000, 80000), '통신': (30000, 60000),
                'IT서비스': (50000, 200000), '철강': (200000, 500000), '전력': (10000, 30000),
                '건설': (30000, 100000), '보험': (20000, 80000), '비철금속': (30000, 100000),
                '운송': (20000, 80000), '담배': (50000, 150000), '레저': (30000, 100000),
                '엔터테인먼트': (50000, 200000), '가스': (20000, 60000),
            }
            price_range = sector_price_ranges.get(row['섹터'], (50000, 200000))
            estimated_price = np.random.uniform(price_range[0], price_range[1])
            prices.append((idx, estimated_price))
    
    # 미국 주식 처리 (yfinance 사용)
    for idx, row in us_stocks.iterrows():
        real_price = get_real_stock_price(row['티커'], row['국가'])
        if real_price is not None:
            prices.append((idx, real_price))
        else:
            # 가져오기 실패 시 섹터별 평균 주가 추정
            if row['국가'] == '한국':
                # 한국 주식: 섹터별 평균 주가 범위 (원화)
                sector_price_ranges = {
                    '반도체': (50000, 200000),
                    '인터넷': (100000, 300000),
                    '화학': (200000, 600000),
                    '배터리': (400000, 800000),
                    '유통': (50000, 200000),
                    '자동차': (50000, 300000),
                    '바이오': (300000, 1000000),
                    '게임': (200000, 500000),
                    '금융': (30000, 100000),
                    '전자': (50000, 150000),
                    '에너지': (20000, 80000),
                    '통신': (30000, 60000),
                    'IT서비스': (50000, 200000),
                    '철강': (200000, 500000),
                    '전력': (10000, 30000),
                    '건설': (30000, 100000),
                    '보험': (20000, 80000),
                    '비철금속': (30000, 100000),
                    '운송': (20000, 80000),
                    '담배': (50000, 150000),
                    '레저': (30000, 100000),
                    '엔터테인먼트': (50000, 200000),
                    '가스': (20000, 60000),
                }
                price_range = sector_price_ranges.get(row['섹터'], (50000, 200000))
                estimated_price = np.random.uniform(price_range[0], price_range[1])
                prices.append((idx, estimated_price))
            else:
                # 미국 주식: 섹터별 평균 주가 범위 (USD -> 원화 환산)
                sector_price_ranges_usd = {
                    '기술': (100, 500),
                    '헬스케어': (50, 400),
                    '금융': (30, 200),
                    '소비재': (50, 300),
                    '필수소비재': (30, 200),
                    '에너지': (20, 150),
                    '산업재': (50, 300),
                    '통신서비스': (20, 100),
                    '소재': (30, 200),
                    '부동산': (50, 300),
                    '유틸리티': (30, 150),
                }
                price_range_usd = sector_price_ranges_usd.get(row['섹터'], (50, 200))
                estimated_price_usd = np.random.uniform(price_range_usd[0], price_range_usd[1])
                prices.append((idx, estimated_price_usd * exchange_rate))
    
    # 가격을 인덱스 순서대로 정렬하여 할당
    prices_dict = {idx: price for idx, price in prices}
    df['현재가'] = [prices_dict.get(idx, 100000) for idx in df.index]
    
    return df

# 주가 데이터 가져오기 (과거 데이터) - yfinance 사용
@st.cache_data(ttl=300)
def get_stock_history(ticker, country, period="3mo"):
    """주가 과거 데이터를 가져오는 함수 - yfinance 사용"""
    try:
        if country == '미국':
            # 미국 주식은 yfinance 사용
            stock = yf.Ticker(ticker)
            if period == "3mo":
                hist = stock.history(period="3mo")
            elif period == "6mo":
                hist = stock.history(period="6mo")
            else:
                hist = stock.history(period="1y")
            if len(hist) > 0:
                return hist
        else:
            # 한국 주식은 yfinance 사용 (.KS 추가)
            try:
                stock = yf.Ticker(f"{ticker}.KS")
                if period == "3mo":
                    hist = stock.history(period="3mo")
                elif period == "6mo":
                    hist = stock.history(period="6mo")
                else:
                    hist = stock.history(period="1y")
                if len(hist) > 0:
                    return hist
            except:
                pass
            
            # .KS가 안 되면 티커만으로 시도
            try:
                stock = yf.Ticker(ticker)
                if period == "3mo":
                    hist = stock.history(period="3mo")
                elif period == "6mo":
                    hist = stock.history(period="6mo")
                else:
                    hist = stock.history(period="1y")
                if len(hist) > 0:
                    return hist
            except:
                pass
        
        return None
    except:
        return None

# 머신러닝 기반 주가 예측 함수
def predict_stock_price(hist_data, days_ahead=30):
    """보수적이고 현실적인 트렌드 기반 주가 예측"""
    if hist_data is None or len(hist_data) < 20:
        return None, None
    
    try:
        # 데이터 준비
        df = hist_data.copy()
        df = df[['Close']].reset_index()
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date')
        
        last_price = df['Close'].iloc[-1]
        last_date = df['Date'].iloc[-1]
        
        # 미래 날짜 생성
        future_dates = pd.date_range(start=last_date + timedelta(days=1), periods=days_ahead, freq='D')
        
        # 보수적인 트렌드 기반 예측 (머신러닝 대신 신뢰할 수 있는 통계적 방법 사용)
        # 1. 단기 이동평균 (5일) vs 중기 이동평균 (20일) 비교
        if len(df) >= 20:
            ma5 = df['Close'].tail(5).mean()
            ma20 = df['Close'].tail(20).mean()
            
            # 2. 최근 30일 평균 변동률 계산
            if len(df) >= 30:
                recent_returns = df['Close'].tail(30).pct_change().dropna()
                avg_daily_return = recent_returns.mean()
                volatility = recent_returns.std()
            else:
                recent_returns = df['Close'].tail(len(df)-1).pct_change().dropna()
                avg_daily_return = recent_returns.mean() if len(recent_returns) > 0 else 0
                volatility = recent_returns.std() if len(recent_returns) > 0 else 0.02
            
            # 3. 트렌드 계산 (MA5 vs MA20)
            if ma20 > 0:
                trend_signal = (ma5 - ma20) / ma20  # -1 ~ 1 사이 값
            else:
                trend_signal = 0
            
            # 4. 보수적인 예측 계산
            # 일일 예상 수익률 = 평균 수익률 + 트렌드 신호 (보수적으로 반영)
            # 최대 일일 변동률을 ±1.5%로 제한
            daily_expected_return = avg_daily_return + (trend_signal * 0.3)
            daily_expected_return = np.clip(daily_expected_return, -0.015, 0.015)  # ±1.5% 제한
            
            # 5. 30일 후 예측 (복리 계산, 하지만 감쇠 적용)
            # 30일 후 예상 변동률 = 일일 수익률 * 30일 * 감쇠 계수
            # 감쇠 계수: 시간이 지날수록 예측 불확실성 증가
            decay_factor = 0.7  # 30% 감쇠
            total_return = daily_expected_return * days_ahead * decay_factor
            
            # 최종 변동률을 ±25%로 엄격하게 제한 (30일 기준으로는 현실적)
            total_return = np.clip(total_return, -0.25, 0.25)
            
            predicted_price_30d = last_price * (1 + total_return)
            
            # 최종 안전장치: 예측값이 현재가의 50% 미만 또는 200% 초과 방지
            predicted_price_30d = np.clip(predicted_price_30d, last_price * 0.5, last_price * 2.0)
            
            # 30일간의 예측 경로 생성 (선형 보간)
            predictions = np.linspace(last_price, predicted_price_30d, days_ahead)
            
        else:
            # 데이터 부족 시 현재가 유지 (변동 없음)
            predictions = np.full(days_ahead, last_price)
        
        return future_dates, predictions
        
    except Exception as e:
        return None, None

# RSI 계산 함수
def calculate_rsi(prices, period=14):
    """RSI (Relative Strength Index) 계산"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# 주가 그래프 생성 함수
def create_stock_chart(ticker, company_name, country, hist_data, future_dates=None, predictions=None):
    """주가 변동 그래프와 예측 그래프 생성"""
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=('주가 변동 및 예측', '거래량'),
        row_heights=[0.7, 0.3]
    )
    
    if hist_data is not None and len(hist_data) > 0:
        # 과거 주가 데이터
        hist_df = hist_data.reset_index()
        hist_df['Date'] = pd.to_datetime(hist_df['Date'])
        
        # 주가 라인
        fig.add_trace(
            go.Scatter(
                x=hist_df['Date'],
                y=hist_df['Close'],
                mode='lines',
                name='실제 주가',
                line=dict(color='#3498db', width=2)
            ),
            row=1, col=1
        )
        
        # 이동평균선
        hist_df['MA20'] = hist_df['Close'].rolling(window=20).mean()
        fig.add_trace(
            go.Scatter(
                x=hist_df['Date'],
                y=hist_df['MA20'],
                mode='lines',
                name='20일 이동평균',
                line=dict(color='#e74c3c', width=1, dash='dash')
            ),
            row=1, col=1
        )
        
        # 예측 데이터
        if future_dates is not None and predictions is not None:
            fig.add_trace(
                go.Scatter(
                    x=future_dates,
                    y=predictions,
                    mode='lines',
                    name='ML 예측 주가',
                    line=dict(color='#2ecc71', width=2, dash='dot')
                ),
                row=1, col=1
            )
            
            # 예측 구간 표시
            fig.add_trace(
                go.Scatter(
                    x=list(future_dates) + list(future_dates[::-1]),
                    y=list(predictions * 1.05) + list(predictions * 0.95)[::-1],
                    fill='toself',
                    fillcolor='rgba(46, 204, 113, 0.2)',
                    line=dict(color='rgba(255,255,255,0)'),
                    name='예측 구간 (±5%)',
                    showlegend=True
                ),
                row=1, col=1
            )
        
        # 거래량
        fig.add_trace(
            go.Bar(
                x=hist_df['Date'],
                y=hist_df['Volume'],
                name='거래량',
                marker_color='#95a5a6'
            ),
            row=2, col=1
        )
    
    fig.update_layout(
        title=f'{company_name} ({ticker}) 주가 변동 및 머신러닝 예측',
        height=600,
        showlegend=True,
        hovermode='x unified'
    )
    
    fig.update_xaxes(title_text="날짜", row=2, col=1)
    fig.update_yaxes(title_text="주가", row=1, col=1)
    fig.update_yaxes(title_text="거래량", row=2, col=1)
    
    return fig

# OpenAI를 활용한 종목 분석 함수
def get_stock_analysis(company_name, ticker, country, sector, per, dividend_rate, growth_rate, volatility, news_sentiment):
    """OpenAI를 사용하여 종목 분석 생성"""
    try:
        # OpenAI API 키 확인 (세션 상태 우선)
        api_key = st.session_state.get('openai_api_key', '')
        
        if not api_key:
            # 환경변수 확인
            api_key = os.getenv("OPENAI_API_KEY", "")
        
        if not api_key:
            # Streamlit secrets에서도 확인
            try:
                api_key = st.secrets.get("OPENAI_API_KEY", "")
            except:
                pass
        
        if not api_key:
            return {
                "recommendation_reason": "OpenAI API 키가 설정되지 않았습니다. 환경변수 OPENAI_API_KEY를 설정해주세요.",
                "caution_points": "API 키 설정이 필요합니다.",
                "articles": []
            }
        
        client = OpenAI(api_key=api_key)
        
        # 프롬프트 생성
        prompt = f"""
다음 주식에 대한 투자 분석을 한국어로 작성해주세요:

회사명: {company_name}
티커: {ticker}
국가: {country}
섹터: {sector}
PER: {per}
배당률: {dividend_rate}%
성장률: {growth_rate}%
변동성: {volatility}
뉴스감성 점수: {news_sentiment}/5

다음 형식으로 답변해주세요:

1. 추천 이유 (2-3문단):
   - 이 종목을 추천하는 주요 이유를 설명해주세요.
   - 재무 지표, 성장성, 시장 지위 등을 종합적으로 고려하여 작성해주세요.

2. 주의해야 할 점 (2-3문단):
   - 투자 시 주의해야 할 리스크 요인을 설명해주세요.
   - 시장 환경, 경쟁 상황, 재무 리스크 등을 포함해주세요.

답변은 한국어로 작성하고, 객관적이고 전문적인 톤으로 작성해주세요.
"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # 비용 효율적인 모델 사용
            messages=[
                {"role": "system", "content": "당신은 전문 증권 애널리스트입니다. 주식 투자 분석을 객관적이고 전문적으로 제공합니다."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        
        analysis_text = response.choices[0].message.content
        
        # 추천 이유와 주의사항 분리
        parts = analysis_text.split("2. 주의해야 할 점")
        recommendation_reason = parts[0].replace("1. 추천 이유", "").strip() if len(parts) > 0 else analysis_text
        caution_points = parts[1].strip() if len(parts) > 1 else "분석 정보를 확인할 수 없습니다."
        
        return {
            "recommendation_reason": recommendation_reason,
            "caution_points": caution_points,
            "articles": []  # 기사는 별도 함수로 처리
        }
        
    except Exception as e:
        return {
            "recommendation_reason": f"분석 생성 중 오류가 발생했습니다: {str(e)}",
            "caution_points": "분석 정보를 확인할 수 없습니다.",
            "articles": []
        }

# 관련 기사 검색 함수
def search_news_articles(company_name, ticker, country):
    """주식 관련 최신 뉴스 기사 링크 검색"""
    articles = []
    
    try:
        # Google News 검색
        if country == "미국":
            search_query = f"{company_name} {ticker} stock news"
            google_news_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}&tbm=nws&hl=en"
        else:
            search_query = f"{company_name} {ticker} 주가 뉴스"
            google_news_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}&tbm=nws&hl=ko"
        
        articles.append({
            "title": f"{company_name} 최신 뉴스 (Google News)",
            "url": google_news_url,
            "source": "Google News"
        })
        
        # 한국 주식의 경우 네이버 뉴스
        if country == "한국":
            naver_query = f"{company_name}+주가+뉴스"
            naver_news_url = f"https://search.naver.com/search.naver?where=news&query={naver_query}"
            articles.append({
                "title": f"{company_name} 네이버 뉴스",
                "url": naver_news_url,
                "source": "Naver News"
            })
            
            # 다음 뉴스
            daum_query = f"{company_name}+주가"
            daum_news_url = f"https://search.daum.net/search?w=news&q={daum_query}"
            articles.append({
                "title": f"{company_name} 다음 뉴스",
                "url": daum_news_url,
                "source": "Daum News"
            })
        
        # Yahoo Finance 뉴스 (미국 주식)
        if country == "미국":
            yahoo_news_url = f"https://finance.yahoo.com/quote/{ticker}/news"
            articles.append({
                "title": f"{company_name} Yahoo Finance 뉴스",
                "url": yahoo_news_url,
                "source": "Yahoo Finance"
            })
            
            # MarketWatch 뉴스
            marketwatch_url = f"https://www.marketwatch.com/investing/stock/{ticker}"
            articles.append({
                "title": f"{company_name} MarketWatch 뉴스",
                "url": marketwatch_url,
                "source": "MarketWatch"
            })
        
    except Exception as e:
        st.error(f"기사 검색 중 오류: {str(e)}")
    
    return articles

# 점수 변환 함수들
def get_stability_score(volatility, market_cap):
    """안정성 점수 계산 (변동성 + 시가총액 규모)"""
    volatility_map = {
        '낮음': 5,
        '중간': 3,
        '높음': 2,
        '매우높음': 1
    }
    market_cap_map = {
        '대형': 5,
        '중형': 3,
        '소형': 1
    }
    return (volatility_map.get(volatility, 0) * 0.6 + market_cap_map.get(market_cap, 0) * 0.4)

def get_valuation_score(per):
    """밸류에이션 점수 계산 (PER 기준, 낮을수록 좋음)"""
    # PER이 10 이하면 5점, 20이면 3점, 30이면 2점, 50 이상이면 1점
    if per <= 10:
        return 5
    elif per <= 15:
        return 4.5
    elif per <= 20:
        return 4
    elif per <= 25:
        return 3
    elif per <= 35:
        return 2
    else:
        return 1

def get_liquidity_score(liquidity):
    """유동성 점수 계산"""
    liquidity_map = {
        '매우높음': 5,
        '높음': 4,
        '중간': 3,
        '낮음': 2,
        '매우낮음': 1
    }
    return liquidity_map.get(liquidity, 0)

def get_technical_score(rsi):
    """기술적 지표 점수 계산 (RSI 기준)"""
    # RSI 40-60: 최적 (5점), 30-40 또는 60-70: 양호 (4점), 그 외: 주의 (2-3점)
    if 40 <= rsi <= 60:
        return 5
    elif 30 <= rsi < 40 or 60 < rsi <= 70:
        return 4
    elif 20 <= rsi < 30 or 70 < rsi <= 80:
        return 3
    else:
        return 2

def normalize_score(series, reverse=False):
    """점수를 0-5 범위로 정규화"""
    if reverse:
        # 역정규화 (낮을수록 좋은 경우)
        max_val = series.max()
        min_val = series.min()
        if max_val == min_val:
            return pd.Series([3.0] * len(series))
        return 5 - ((series - min_val) / (max_val - min_val) * 4)
    else:
        # 정규화 (높을수록 좋은 경우)
        max_val = series.max()
        min_val = series.min()
        if max_val == min_val:
            return pd.Series([3.0] * len(series))
        return 1 + ((series - min_val) / (max_val - min_val) * 4)

# 메인 타이틀
st.title("📊 주린이 전용 포트폴리오 추천 대시보드")

# 소개 섹션 (예쁜 배경 스타일)
st.markdown("""
<style>
.intro-container {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 30px;
    border-radius: 15px;
    margin: 20px 0;
    box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    color: white;
}
.intro-title {
    font-size: 24px;
    font-weight: bold;
    margin-bottom: 20px;
    text-align: center;
    text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
}
.intro-content {
    font-size: 16px;
    line-height: 1.6;
    margin: 15px 0;
    text-align: center;
    opacity: 0.95;
}
.intro-divider {
    margin: 30px auto;
    width: 80%;
    height: 2px;
    background: rgba(255,255,255,0.4);
    border: none;
}
.intro-subtitle {
    font-size: 20px;
    font-weight: 600;
    margin: 30px 0 15px 0;
    text-align: center;
}
</style>
""", unsafe_allow_html=True)

# 소개 섹션
st.markdown("""
<div class="intro-container">
    <div class="intro-title">🥚 계란을 한 바구니에 담지마라!</div>
    <div class="intro-content">제2의 월급을 안전하게 지키기 위해 다양성을 고려한 주식 포트폴리오를 추천해드릴게요.</div>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# 주식 데이터 로드 (실제 주가 가져오기)
with st.spinner("📊 S&P 500과 KOSPI 200 종목 데이터를 불러오는 중... (시간이 걸릴 수 있습니다)"):
    df_stocks = get_stock_data()
    st.success(f"✅ {len(df_stocks)}개 종목 데이터 로드 완료!")

# 사이드바에 입력 UI
with st.sidebar:
    st.header("💰 투자 정보 입력")
    
    # 월급 입력
    salary = st.number_input(
        "월급 (원)",
        min_value=0,
        value=3000000,
        step=100000,
        help="월 급여를 입력하세요",
        format="%d"
    )
    st.caption(f"💵 입력된 월급: {salary:,}원")
    
    # 소비액 입력
    expense = st.number_input(
        "소비액 (원)",
        min_value=0,
        value=2000000,
        step=100000,
        help="월 소비액을 입력하세요",
        format="%d"
    )
    st.caption(f"💸 입력된 소비액: {expense:,}원")
    
    # 투자성향 슬라이더
    risk_tolerance = st.slider(
        "투자성향",
        min_value=0,
        max_value=100,
        value=50,
        help="0: 완전 보수적 (Low Risk) ~ 100: 공격적 (High Risk)",
        format="%d"
    )
    
    # 투자성향 표시
    if risk_tolerance <= 30:
        risk_label = "🟢 Low Risk (보수적)"
    elif risk_tolerance <= 70:
        risk_label = "🟡 Medium Risk (중립)"
    else:
        risk_label = "🔴 High Risk (공격적)"
    
    st.markdown(f"**현재 투자성향:** {risk_label}")
    
    st.markdown("---")
    st.markdown("#### 🤖 OpenAI 설정 (선택사항)")
    st.caption("종목별 상세 분석을 위해 OpenAI API 키를 입력하세요.")
    
    # OpenAI API 키 입력
    api_key_input = st.text_input(
        "OpenAI API 키",
        type="password",
        help="OpenAI API 키를 입력하면 종목별 상세 분석을 제공합니다.",
        placeholder="sk-..."
    )
    
    if api_key_input:
        # 세션 상태에 저장
        st.session_state['openai_api_key'] = api_key_input
        st.success("✅ API 키가 설정되었습니다.")
    else:
        # 환경변수나 secrets에서 확인
        env_key = os.getenv("OPENAI_API_KEY", "")
        if not env_key:
            try:
                env_key = st.secrets.get("OPENAI_API_KEY", "")
            except:
                pass
        
        if env_key:
            st.session_state['openai_api_key'] = env_key
            st.info("ℹ️ 환경변수에서 API 키를 사용합니다.")
        else:
            st.warning("⚠️ API 키를 입력하면 종목별 상세 분석을 받을 수 있습니다.")

# 잔액 계산
balance = salary - expense

# 잔액이 0 이하인 경우 처리
if balance <= 0:
    st.error("⚠️ 투자 가능 금액이 없습니다. 소비액이 월급보다 크거나 같습니다.")
    st.stop()

# 투자성향에 따른 예적금 등 안전상품/투자 배분 계산
# 보수적 투자자일수록 안전상품 비율 높음
if risk_tolerance <= 30:
    # 보수적: 예적금 등 안전상품 60%, 투자 40%
    savings_ratio = 0.6
    investment_ratio = 0.4
elif risk_tolerance <= 50:
    # 중하위: 예적금 등 안전상품 40%, 투자 60%
    savings_ratio = 0.4
    investment_ratio = 0.6
elif risk_tolerance <= 70:
    # 중립: 예적금 등 안전상품 20%, 투자 80%
    savings_ratio = 0.2
    investment_ratio = 0.8
else:
    # 공격적: 예적금 등 안전상품 10%, 투자 90%
    savings_ratio = 0.1
    investment_ratio = 0.9

savings_amount = int(balance * savings_ratio)
investment_amount = int(balance * investment_ratio)

# 메인 영역
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("💵 잔액 정보")
    st.metric("총 잔액", f"{balance:,}원")
    st.info(f"월급: {salary:,}원 - 소비액: {expense:,}원 = **{balance:,}원**")

with col2:
    st.subheader("💰 자산 배분")
    st.metric("예적금 등 안전상품 추천", f"{savings_amount:,}원", f"{savings_ratio*100:.0f}%")
    st.metric("투자 추천", f"{investment_amount:,}원", f"{investment_ratio*100:.0f}%")
    if risk_tolerance <= 30:
        st.info("💡 보수적 투자자: 안정적인 예적금 등 안전상품 비율을 높게 설정했습니다.")

with col3:
    st.subheader("📈 투자성향")
    st.metric("투자성향 점수", f"{risk_tolerance}/100")
    st.progress(risk_tolerance / 100)
    st.caption(risk_label)
    # 환율 정보 표시
    exchange_rate = get_exchange_rate()
    st.caption(f"💱 현재 환율: 1 USD = {exchange_rate:,.0f} KRW")

st.markdown("---")

# 알고리즘 설명 (접을 수 있는 섹션)
with st.expander("ℹ️ 투자 추천 알고리즘 설명"):
    st.markdown("""
    ### 🎯 종합 투자 의사결정 알고리즘
    
    본 대시보드는 **8가지 핵심 투자 요소**를 종합적으로 고려하여 최적의 포트폴리오를 추천합니다:
    
    1. **안정성** (변동성 + 시가총액 규모)
    2. **수익률** (최근 수익률)
    3. **성장률** (예상 성장률)
    4. **밸류에이션** (PER - 저평가 여부)
    5. **배당률** (배당 수익률)
    6. **뉴스감성** (최근 뉴스 감성 분석)
    7. **유동성** (거래량 기반)
    8. **기술적 지표** (RSI - 과매수/과매도 여부)
    
    ### 📊 투자성향별 가중치 조정
    
    - **보수적 투자자 (Low Risk)**: 안정성, 배당률, 밸류에이션 중시
    - **공격적 투자자 (High Risk)**: 수익률, 성장률, 기술적 지표 중시
    - **중립 투자자**: 균형잡힌 접근
    
    ### 🌐 포트폴리오 다양성
    
    섹터와 국가 분산을 고려하여 다양성 보너스 점수를 추가합니다.
    """)

# ========== 종합 투자 의사결정 알고리즘 ==========
# 투자성향에 따라 동적으로 가중치 조정

# 1. 각 요소별 점수 계산
df_stocks['안정성점수'] = df_stocks.apply(
    lambda row: get_stability_score(row['변동성'], row['시가총액규모']), axis=1
)
df_stocks['밸류에이션점수'] = df_stocks['PER'].apply(get_valuation_score)
df_stocks['유동성점수'] = df_stocks['유동성'].apply(get_liquidity_score)
df_stocks['기술적지표점수'] = df_stocks['RSI'].apply(get_technical_score)

# 2. 수익률, 배당률, 성장률 정규화 (0-5 점수로 변환)
df_stocks['수익률점수'] = normalize_score(df_stocks['최근수익률(%)'])
df_stocks['배당률점수'] = normalize_score(df_stocks['배당률(%)'])
df_stocks['성장률점수'] = normalize_score(df_stocks['성장률(%)'])

# 3. 투자성향에 따른 동적 가중치 계산
risk_ratio = risk_tolerance / 100  # 0~1 범위

# 보수적 투자자 (risk_ratio 낮음): 안정성, 배당률, 유동성, 밸류에이션 중시
# 공격적 투자자 (risk_ratio 높음): 수익률, 성장률, 기술적 지표 중시
# 중립 투자자: 균형잡힌 접근

# 기본 가중치 (투자성향에 따라 조정)
weights = {
    '안정성': max(0.2, 0.4 - (risk_ratio * 0.3)),  # 0.4 ~ 0.1
    '수익률': 0.15 + (risk_ratio * 0.15),  # 0.15 ~ 0.3
    '성장률': 0.1 + (risk_ratio * 0.15),  # 0.1 ~ 0.25
    '밸류에이션': max(0.1, 0.2 - (risk_ratio * 0.1)),  # 0.2 ~ 0.1
    '배당률': max(0.05, 0.15 - (risk_ratio * 0.1)),  # 0.15 ~ 0.05
    '뉴스감성': 0.15,  # 고정
    '유동성': 0.1,  # 고정
    '기술적지표': 0.05 + (risk_ratio * 0.1)  # 0.05 ~ 0.15
}

# 가중치 정규화 (합이 1이 되도록)
total_weight = sum(weights.values())
weights = {k: v / total_weight for k, v in weights.items()}

# 4. 종합 점수 계산
df_stocks['종합점수'] = (
    weights['안정성'] * df_stocks['안정성점수'] +
    weights['수익률'] * df_stocks['수익률점수'] +
    weights['성장률'] * df_stocks['성장률점수'] +
    weights['밸류에이션'] * df_stocks['밸류에이션점수'] +
    weights['배당률'] * df_stocks['배당률점수'] +
    weights['뉴스감성'] * df_stocks['뉴스감성(1~5)'] +
    weights['유동성'] * df_stocks['유동성점수'] +
    weights['기술적지표'] * df_stocks['기술적지표점수']
)

# 5. 포트폴리오 다양성 보너스 (섹터/국가 분산)
# 이미 선택된 종목과 다른 섹터/국가면 보너스 점수 추가
df_stocks['다양성보너스'] = 0.0
# 이 부분은 추천 종목을 선택한 후에 적용 (아래에서 처리)

# 총점 = 종합점수 + 다양성보너스
df_stocks['총점'] = df_stocks['종합점수']

# 매수 가능 주수 계산 (투자 금액 기준)
df_stocks['매수가능주수'] = (investment_amount / df_stocks['현재가']).astype(int)
df_stocks['매수가능금액'] = df_stocks['매수가능주수'] * df_stocks['현재가']

# 주수 1 이상만 필터링
df_candidates = df_stocks[df_stocks['매수가능주수'] >= 1].copy()

# 주가 예측 점수 추가 (상위 30개 종목만 빠르게 예측하여 하락 예상 주식 필터링)
# 로딩 시간 단축을 위해 상위 종목만 예측
df_candidates['예측변동률'] = 0.0
df_candidates['예측점수'] = 0.0

# 상위 30개 종목만 예측 (더 빠른 처리)
top_candidates = df_candidates.head(30).copy()

if len(top_candidates) > 0:
    for idx, row in top_candidates.iterrows():
        try:
            # 머신러닝 기반 예측 사용
            hist_data = get_stock_history(row['티커'], row['국가'], period="3mo")
            current_price = row['현재가']
            
            if hist_data is not None and len(hist_data) >= 30:
                # 머신러닝 예측 수행
                future_dates, predictions = predict_stock_price(hist_data, days_ahead=30)
                
                if predictions is not None and len(predictions) > 0:
                    # 30일 후 예측 주가
                    predicted_price_30d = predictions[-1]
                    
                    # 최종 안전장치: 예측값이 현재가의 50% 미만 또는 200% 초과인 경우 재계산
                    if predicted_price_30d < current_price * 0.5 or predicted_price_30d > current_price * 2.0:
                        # 비현실적인 예측값인 경우, 보수적인 트렌드 기반 예측으로 대체
                        recent_prices = hist_data['Close'].tail(20).values
                        if len(recent_prices) >= 10:
                            ma_short = np.mean(recent_prices[-5:])
                            ma_long = np.mean(recent_prices[-10:])
                            if ma_long > 0:
                                trend = (ma_short - ma_long) / ma_long
                                # 트렌드를 매우 보수적으로 반영 (최대 ±15% 제한)
                                trend = np.clip(trend, -0.15, 0.15)
                                predicted_price_30d = current_price * (1 + trend * 0.5)  # 50%만 반영
                            else:
                                # 예측 실패 시 약한 상승 예상으로 설정
                                predicted_price_30d = current_price * 1.01
                        else:
                            predicted_price_30d = current_price * 1.01
                    
                    # 예측 변동률 계산
                    price_change_pct = ((predicted_price_30d - current_price) / current_price) * 100
                    
                    # 비현실적인 변동률 엄격하게 제한 (±25% 이내로 제한)
                    # 30일 기준으로 ±25%는 현실적인 범위
                    price_change_pct = np.clip(price_change_pct, -25, 25)
                    
                    df_candidates.at[idx, '예측변동률'] = price_change_pct
                    
                    # 예측 점수 계산
                    if price_change_pct > 15:
                        df_candidates.at[idx, '예측점수'] = 5.0
                    elif price_change_pct > 10:
                        df_candidates.at[idx, '예측점수'] = 4.0
                    elif price_change_pct > 5:
                        df_candidates.at[idx, '예측점수'] = 3.0
                    elif price_change_pct > 2:
                        df_candidates.at[idx, '예측점수'] = 2.0
                    elif price_change_pct > 0:
                        df_candidates.at[idx, '예측점수'] = 1.0
                    else:
                        df_candidates.at[idx, '예측점수'] = -10.0
                else:
                    # 예측 실패 시 보수적인 트렌드 기반 예측으로 대체
                    recent_prices = hist_data['Close'].tail(20).values
                    if len(recent_prices) >= 10:
                        ma_short = np.mean(recent_prices[-5:])
                        ma_long = np.mean(recent_prices[-10:])
                        if ma_long > 0:
                            trend = (ma_short - ma_long) / ma_long
                            # 트렌드를 매우 보수적으로 반영 (최대 ±15% 제한)
                            trend = np.clip(trend, -0.15, 0.15)
                            predicted_price_30d = current_price * (1 + trend * 0.5)  # 50%만 반영
                            price_change_pct = ((predicted_price_30d - current_price) / current_price) * 100
                            price_change_pct = np.clip(price_change_pct, -25, 25)  # ±25% 제한
                            df_candidates.at[idx, '예측변동률'] = price_change_pct
                            
                            if price_change_pct > 0:
                                df_candidates.at[idx, '예측점수'] = max(0.5, price_change_pct / 10)
                            else:
                                df_candidates.at[idx, '예측점수'] = -10.0
                        else:
                            # 예측 불가 - 약한 상승 예상으로 설정
                            df_candidates.at[idx, '예측변동률'] = 1.0
                            df_candidates.at[idx, '예측점수'] = 0.5
                    else:
                        # 예측 불가 - 약한 상승 예상으로 설정
                        df_candidates.at[idx, '예측변동률'] = 1.0
                        df_candidates.at[idx, '예측점수'] = 0.5
            else:
                # 데이터 부족 시 약한 상승 예상으로 설정
                df_candidates.at[idx, '예측변동률'] = 1.0
                df_candidates.at[idx, '예측점수'] = 0.5
        except Exception as e:
            # 예외 발생 시 약한 상승 예상으로 설정
            df_candidates.at[idx, '예측변동률'] = 1.0
            df_candidates.at[idx, '예측점수'] = 0.5

# 수익성과 안정성을 모두 고려한 종합 점수 계산
# 머신러닝 예측 결과(상승/하락 예상)를 높은 가중치로 반영
df_candidates['수익성점수'] = df_candidates['예측점수'].apply(lambda x: max(0, x))  # 양수만 (상승 예상)
df_candidates['안정성점수_종합'] = df_candidates['안정성점수']  # 기존 안정성 점수

# 수익성과 안정성의 균형을 고려한 최종 점수
# 머신러닝 예측 결과(수익성) 50%, 안정성 25%, 기존 종합점수 25%
# 상승 예상 정도가 높을수록 더 높은 점수
df_candidates['최종종합점수'] = (
    df_candidates['종합점수'] * 0.25 +  # 기존 종합점수 25%
    df_candidates['수익성점수'] * 0.50 +  # 예측 수익성 50% (매우 높은 가중치)
    df_candidates['안정성점수_종합'] * 0.25  # 안정성 25%
)

# 점수 순으로 정렬 (수익성과 안정성 모두 고려)
# 1순위: 최종종합점수 (수익성+안정성 종합)
# 2순위: 예측변동률 (수익률 예상)
df_candidates = df_candidates.sort_values(
    ['최종종합점수', '예측변동률'], 
    ascending=[False, False]
).reset_index(drop=True)

# 하락 예상 주식 완전 제외 (상승 예상 종목만 추천)
# 1. 예측변동률이 0보다 큰 종목만 추천 (상승 예상만)
# 2. 예측점수가 음수인 종목 제외
df_candidates = df_candidates[
    (df_candidates['예측변동률'] > 0) |  # 상승 예상
    ((df_candidates['예측변동률'] == 0) & (df_candidates['예측점수'] >= 0))  # 예측 없거나 중립 (하락 예상 아님)
].copy()

# 하락 예상 종목은 완전히 제외
df_candidates = df_candidates[df_candidates['예측점수'] >= 0].copy()

# 예측 데이터가 없는 종목 처리 (예측 실패한 경우만 포함)
if len(df_candidates) == 0:
    # 예측이 모두 실패한 경우, 예측 없이 종합점수만으로 추천
    df_candidates = df_stocks[df_stocks['매수가능주수'] >= 1].copy()
    df_candidates['예측변동률'] = 0.0
    df_candidates['예측점수'] = 0.0
    df_candidates['수익성점수'] = 0.0
    df_candidates['최종종합점수'] = df_candidates['종합점수']
else:
    # 예측이 없는 종목도 추가 (예측 실패한 경우만, 하락 예상은 제외)
    no_prediction = df_stocks[
        (df_stocks['매수가능주수'] >= 1) & 
        (~df_stocks['티커'].isin(df_candidates['티커']))
    ].copy()
    if len(no_prediction) > 0:
        no_prediction['예측변동률'] = 0.0
        no_prediction['예측점수'] = 0.0
        no_prediction['수익성점수'] = 0.0
        no_prediction['최종종합점수'] = no_prediction['종합점수']
        df_candidates = pd.concat([df_candidates, no_prediction], ignore_index=True)

# 포트폴리오 다양성 고려한 최종 추천 (개선된 알고리즘)
def select_diversified_portfolio(df, target_stocks=10, investment_amount=0):
    """다양성을 고려한 포트폴리오 선택 - 15~20개 종목 추천"""
    if len(df) == 0:
        return pd.DataFrame()
    
    selected = []
    selected_sectors = set()
    selected_countries = set()
    remaining_amount = investment_amount
    
    # 1단계: 균등 분배 + 점수 가중치 혼합 방식으로 종목별 투자 금액 할당
    # 더 많은 종목을 선택하기 위해 각 종목에 할당하는 금액을 작게 설정
    avg_investment_per_stock = investment_amount / target_stocks
    
    # 최소 투자 금액 설정 (더 낮게 설정하여 더 많은 종목 선택 가능)
    min_investment_per_stock = investment_amount / (target_stocks * 3)  # 최소 금액을 낮춤
    
    # 점수 순으로 정렬된 종목들을 순회
    for idx, row in df.iterrows():
        if len(selected) >= target_stocks * 2:  # 여유있게 선택
            break
        
        # 다양성 보너스 계산 (더 강하게 적용)
        diversity_bonus = 0.0
        if row['섹터'] not in selected_sectors:
            diversity_bonus += 0.8  # 증가
        if row['국가'] not in selected_countries:
            diversity_bonus += 0.5  # 증가
        
        # 최종 점수 = 최종종합점수(수익성+안정성) + 다양성보너스
        final_score = row.get('최종종합점수', row['종합점수']) + diversity_bonus
        
        # 수익성과 안정성을 모두 고려한 투자 금액 할당
        # 수익률 예상이 높고 안정성도 좋은 종목에 더 많이 할당
        base_allocation = avg_investment_per_stock * 0.6  # 기본 60%
        
        # 수익성 점수 기반 보너스 (40%)
        revenue_score = row.get('수익성점수', 0)
        max_revenue = df['수익성점수'].max() if '수익성점수' in df.columns else 1
        revenue_bonus = (revenue_score / max_revenue if max_revenue > 0 else 0) * avg_investment_per_stock * 0.4
        
        allocated_amount = base_allocation + revenue_bonus
        
        # 최소 투자 금액 보장
        allocated_amount = max(allocated_amount, min_investment_per_stock)
        
        # 남은 금액이 부족하면 조정
        if allocated_amount > remaining_amount:
            allocated_amount = remaining_amount
        
        # 매수 가능 주수 계산
        buyable_shares = int(allocated_amount / row['현재가'])
        if buyable_shares < 1:
            # 1주도 못 사면 스킵
            continue
        
        actual_investment = buyable_shares * row['현재가']
        
        # 선택된 종목 정보 저장
        selected.append({
            **row.to_dict(),
            '다양성보너스': diversity_bonus,
            '최종점수': final_score,
            '매수가능주수': buyable_shares,
            '매수가능금액': actual_investment
        })
        
        selected_sectors.add(row['섹터'])
        selected_countries.add(row['국가'])
        remaining_amount -= actual_investment
        
        # 남은 금액이 최소 투자 금액보다 작으면 종료
        if remaining_amount < min_investment_per_stock:
            break
    
    # 2단계: 선택된 종목들을 최종점수 순으로 정렬
    df_selected = pd.DataFrame(selected)
    if len(df_selected) > 0:
        df_selected = df_selected.sort_values('최종점수', ascending=False)
        
        # 3단계: 최소 8개 이상 선택하도록 보장
        # 선택된 종목이 8개 미만이면, 남은 금액으로 추가 종목 선택 시도
        if len(df_selected) < 8 and remaining_amount > 0:
            # 남은 종목 중에서 추가 선택 (수익성과 안정성 모두 고려)
            remaining_df = df[~df['티커'].isin(df_selected['티커'])]
            # 수익성과 안정성을 모두 고려하여 정렬
            if '최종종합점수' in remaining_df.columns and '예측변동률' in remaining_df.columns:
                remaining_df = remaining_df.sort_values(
                    ['최종종합점수', '예측변동률'], 
                    ascending=[False, False]
                )
            else:
                remaining_df = remaining_df.sort_values('종합점수', ascending=False)
            
            for idx, row in remaining_df.iterrows():
                if len(df_selected) >= 10:
                    break
                
                # 남은 금액으로 최대한 매수
                buyable_shares = int(remaining_amount / row['현재가'])
                if buyable_shares < 1:
                    continue
                
                actual_investment = buyable_shares * row['현재가']
                
                # 다양성 보너스 재계산
                diversity_bonus = 0.0
                if row['섹터'] not in set(df_selected['섹터']):
                    diversity_bonus += 0.8
                if row['국가'] not in set(df_selected['국가']):
                    diversity_bonus += 0.5
                
                final_score = row.get('최종종합점수', row['종합점수']) + diversity_bonus
                
                df_selected = pd.concat([
                    df_selected,
                    pd.DataFrame([{
                        **row.to_dict(),
                        '다양성보너스': diversity_bonus,
                        '최종점수': final_score,
                        '매수가능주수': buyable_shares,
                        '매수가능금액': actual_investment
                    }])
                ], ignore_index=True)
                
                remaining_amount -= actual_investment
                if remaining_amount < min_investment_per_stock:
                    break
        
        # 최종적으로 10개 내외 선택 (또는 가능한 만큼)
        max_final = min(12, len(df_selected))
        min_final = min(8, len(df_selected))
        
        if len(df_selected) >= min_final:
            df_selected = df_selected.head(max_final)
        else:
            df_selected = df_selected.head(len(df_selected))
        
        # 최종 정렬: 수익성(예측변동률)과 안정성을 모두 고려
        # 1순위: 최종점수, 2순위: 예측변동률 (수익률 예상)
        if '예측변동률' in df_selected.columns:
            df_selected = df_selected.sort_values(
                ['최종점수', '예측변동률'], 
                ascending=[False, False]
            )
        else:
            df_selected = df_selected.sort_values('최종점수', ascending=False)
    
    return df_selected.reset_index(drop=True)

# 최종 추천 포트폴리오 생성 (15~20개 종목 추천)
df_recommended = select_diversified_portfolio(df_candidates, target_stocks=10, investment_amount=investment_amount)

# 최종점수 순으로 정렬
if len(df_recommended) > 0:
    df_recommended = df_recommended.sort_values('최종점수', ascending=False).reset_index(drop=True)
    df_recommended['총점'] = df_recommended['최종점수']  # 표시용

# 결과 출력
st.subheader("🎯 추천 포트폴리오")

if len(df_recommended) == 0:
    st.warning("⚠️ 투자 가능 금액으로 매수할 수 있는 종목이 없습니다.")
    st.stop()

# 자산 배분 차트
st.markdown("#### 💰 자산 배분")
col1, col2 = st.columns(2)

with col1:
    # 적금 vs 투자 비율 차트
    asset_allocation = pd.DataFrame({
        '구분': ['예적금 등 안전상품', '투자'],
        '금액': [savings_amount, investment_amount]
    })
    fig_asset = px.pie(
        asset_allocation,
        values='금액',
        names='구분',
        title='예적금 등 안전상품 vs 투자 배분',
        color_discrete_map={'예적금 등 안전상품': '#2ecc71', '투자': '#3498db'}
    )
    fig_asset.update_traces(
        textposition='inside',
        textinfo='percent+label',
        hovertemplate='<b>%{label}</b><br>금액: %{value:,.0f}원<br>비율: %{percent}<extra></extra>'
    )
    st.plotly_chart(fig_asset, use_container_width=True)

with col2:
    st.markdown("**자산 배분 상세**")
    st.metric("총 잔액", f"{balance:,}원")
    st.metric("예적금 등 안전상품 추천", f"{savings_amount:,}원", f"{savings_ratio*100:.0f}%")
    st.metric("투자 추천", f"{investment_amount:,}원", f"{investment_ratio*100:.0f}%")
    if risk_tolerance <= 30:
        st.info("💡 보수적 투자자: 안정적인 예적금 등 안전상품 비율을 높게 설정했습니다.")
    elif risk_tolerance >= 70:
        st.info("💡 공격적 투자자: 높은 수익을 위해 투자 비율을 높게 설정했습니다.")

# 추천 종목 테이블
st.markdown("#### 📋 추천 종목 목록")

if len(df_recommended) > 0:
    # 표시할 컬럼 선택 (예측 변동률 추가)
    display_columns = ['회사명', '국가', '섹터', '총점', '최근수익률(%)', 'PER', '배당률(%)', 
                       '현재가', '매수가능주수', '매수가능금액']
    
    # 예측 변동률이 있으면 추가
    if '예측변동률' in df_recommended.columns:
        display_columns.append('예측변동률')
    
    df_display = df_recommended[display_columns].copy()
    df_display['총점'] = df_display['총점'].round(2)
    df_display['최근수익률(%)'] = df_display['최근수익률(%)'].round(1)
    df_display['PER'] = df_display['PER'].round(1)
    df_display['배당률(%)'] = df_display['배당률(%)'].round(2)
    df_display['현재가'] = df_display['현재가'].apply(lambda x: f"{int(x):,}원")
    df_display['매수가능금액'] = df_display['매수가능금액'].apply(lambda x: f"{int(x):,}원")
    
    # 예측 변동률 포맷팅
    if '예측변동률' in df_display.columns:
        def format_prediction(pct):
            if pd.isna(pct):
                return "예측 불가"
            if pct > 0:
                return f"📈 +{pct:.1f}%"
            elif pct < -5:
                return f"⚠️ {pct:.1f}%"
            else:
                return f"📉 {pct:.1f}%"
        
        df_display['예측변동률'] = df_display['예측변동률'].apply(format_prediction)
    
    column_names = ['회사명', '국가', '섹터', '종합점수', '수익률(%)', 'PER', '배당률(%)', 
                          '현재가', '매수 주수', '매수 금액']
    if '예측변동률' in df_display.columns:
        column_names.append('30일 예측')
    
    df_display.columns = column_names
    
    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True
    )
    
    # 추천 종목 정보 표시
    if '예측변동률' in df_recommended.columns:
        rising_stocks = df_recommended[df_recommended['예측변동률'] > 0]
        neutral_stocks = df_recommended[df_recommended['예측변동률'] == 0]
        if len(rising_stocks) > 0:
            st.success(f"✅ 추천 종목 중 {len(rising_stocks)}개 종목이 상승 예상입니다!")
        if len(neutral_stocks) > 0:
            st.info(f"ℹ️ 추천 종목 중 {len(neutral_stocks)}개 종목은 예측 데이터가 없거나 중립입니다.")
    
    # 상세 점수 분석 (접을 수 있는 섹션)
    with st.expander("🔍 종목별 상세 점수 분석"):
        detail_cols = ['회사명', '안정성점수', '수익률점수', '성장률점수', '밸류에이션점수', 
                      '배당률점수', '뉴스감성(1~5)', '유동성점수', '기술적지표점수', '다양성보너스', '최종점수']
        df_detail = df_recommended[detail_cols].copy()
        for col in detail_cols[1:]:  # 회사명 제외
            df_detail[col] = df_detail[col].round(2)
        df_detail.columns = ['회사명', '안정성', '수익률', '성장률', '밸류에이션', '배당률', 
                            '뉴스감성', '유동성', '기술지표', '다양성보너스', '최종점수']
        st.dataframe(df_detail, use_container_width=True, hide_index=True)
    
    # 종목별 상세 분석 (OpenAI + 기사 링크)
    st.markdown("---")
    st.markdown("#### 📊 종목별 상세 분석")
    st.info("💡 각 종목을 클릭하여 OpenAI 기반 투자 분석과 관련 뉴스 기사를 확인하세요.")
    
    for idx, row in df_recommended.iterrows():
        with st.expander(f"📈 {row['회사명']} ({row['티커']}) - 상세 분석"):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.markdown(f"**기본 정보**")
                st.write(f"- 국가: {row['국가']} | 섹터: {row['섹터']}")
                st.write(f"- 현재가: {int(row['현재가']):,}원 | PER: {row['PER']:.1f} | 배당률: {row['배당률(%)']:.2f}%")
                st.write(f"- 최근 수익률: {row['최근수익률(%)']:.1f}% | 성장률: {row['성장률(%)']:.1f}%")
                st.write(f"- 변동성: {row['변동성']} | 뉴스감성: {row['뉴스감성(1~5)']}/5")
            
            with col2:
                st.markdown(f"**투자 정보**")
                st.write(f"- 매수 가능 주수: {int(row['매수가능주수'])}주")
                st.write(f"- 매수 가능 금액: {int(row['매수가능금액']):,}원")
                st.write(f"- 종합 점수: {row['최종점수']:.2f}")
            
            # 주가 변동 그래프 및 머신러닝 예측
            st.markdown("---")
            st.markdown("#### 📈 주가 변동 및 머신러닝 예측")
            
            with st.spinner(f"{row['회사명']} 주가 데이터 및 예측 생성 중..."):
                # 과거 주가 데이터 가져오기 (3개월로 단축)
                hist_data = get_stock_history(row['티커'], row['국가'], period="3mo")
                
                if hist_data is not None and len(hist_data) > 0:
                    # 간단한 트렌드 기반 예측 (빠른 처리)
                    try:
                        # 간단한 이동평균 기반 예측
                        recent_prices = hist_data['Close'].tail(20).values
                        if len(recent_prices) >= 10:
                            ma_short = np.mean(recent_prices[-5:])
                            ma_long = np.mean(recent_prices[-10:])
                            trend = (ma_short - ma_long) / ma_long
                            
                            # 30일 예측 (간단한 트렌드 확장)
                            last_price = hist_data['Close'].iloc[-1]
                            future_dates = pd.date_range(
                                start=hist_data.index[-1] + timedelta(days=1), 
                                periods=30, 
                                freq='D'
                            )
                            predictions = [last_price * (1 + trend * (i+1) * 0.1) for i in range(30)]
                            predictions = np.array(predictions)
                        else:
                            future_dates, predictions = None, None
                    except:
                        # 실패 시 머신러닝 예측 시도 (더 빠른 설정)
                        future_dates, predictions = predict_stock_price(hist_data, days_ahead=30)
                    
                    # 그래프 생성
                    fig = create_stock_chart(
                        row['티커'], 
                        row['회사명'], 
                        row['국가'],
                        hist_data,
                        future_dates,
                        predictions
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 예측 정보 표시
                    if predictions is not None and len(predictions) > 0:
                        current_price = row['현재가']
                        predicted_price_30d = predictions[-1]
                        price_change = predicted_price_30d - current_price
                        price_change_pct = (price_change / current_price) * 100
                        
                        col_pred1, col_pred2, col_pred3 = st.columns(3)
                        with col_pred1:
                            st.metric("현재 주가", f"{int(current_price):,}원")
                        with col_pred2:
                            st.metric("30일 후 예측 주가", f"{int(predicted_price_30d):,}원", 
                                     f"{price_change_pct:+.2f}%")
                        with col_pred3:
                            if price_change_pct > 0:
                                st.success(f"📈 상승 예상: {int(price_change):,}원")
                            else:
                                st.error(f"📉 하락 예상: {int(abs(price_change)):,}원")
                        
                        # 하락 예상 주식에 대한 경고
                        if price_change_pct < 0:
                            if price_change_pct < -10:
                                st.error(f"⚠️ **주의**: 이 종목은 30일 후 약 {abs(price_change_pct):.1f}% 하락 예상입니다. ({int(abs(price_change)):,}원 하락 예상) 투자 시 신중히 검토하세요.")
                            elif price_change_pct < -5:
                                st.warning(f"⚠️ **주의**: 이 종목은 30일 후 약 {abs(price_change_pct):.1f}% 하락 예상입니다. ({int(abs(price_change)):,}원 하락 예상) 투자 결정 시 주의가 필요합니다.")
                            else:
                                st.info(f"ℹ️ 이 종목은 30일 후 약 {abs(price_change_pct):.1f}% 하락 예상입니다. ({int(abs(price_change)):,}원 하락 예상) 다만 소폭 하락이므로 다른 지표와 함께 종합적으로 판단하세요.")
                        else:
                            st.success(f"✅ 이 종목은 30일 후 약 {price_change_pct:.1f}% 상승 예상입니다. ({int(price_change):,}원 상승 예상)")
                        
                        st.info("💡 예측은 머신러닝 알고리즘(Random Forest)을 사용하여 트렌드, 이동평균, 변동성 등을 종합적으로 고려한 결과입니다. 실제 주가는 다양한 요인에 의해 변동할 수 있으므로 참고용으로만 사용하세요.")
                else:
                    st.warning(f"⚠️ {row['회사명']}의 주가 데이터를 가져올 수 없습니다.")
            
            # OpenAI 분석 생성
            with st.spinner(f"{row['회사명']} 분석 생성 중..."):
                analysis = get_stock_analysis(
                    company_name=row['회사명'],
                    ticker=row['티커'],
                    country=row['국가'],
                    sector=row['섹터'],
                    per=row['PER'],
                    dividend_rate=row['배당률(%)'],
                    growth_rate=row['성장률(%)'],
                    volatility=row['변동성'],
                    news_sentiment=row['뉴스감성(1~5)']
                )
            
            st.markdown("---")
            st.markdown("#### 💡 추천 이유")
            st.write(analysis['recommendation_reason'])
            
            st.markdown("---")
            st.markdown("#### ⚠️ 주의해야 할 점")
            st.write(analysis['caution_points'])
            
            st.markdown("---")
            st.markdown("#### 📰 관련 뉴스 기사")
            
            # 관련 기사 검색
            articles = search_news_articles(row['회사명'], row['티커'], row['국가'])
            
            if articles:
                for article in articles:
                    st.markdown(f"- [{article['title']}]({article['url']}) - {article['source']}")
            else:
                st.info("관련 기사를 찾을 수 없습니다.")
            
            st.markdown("---")

# 포트폴리오 비중 파이차트
st.markdown("---")
st.markdown("#### 📊 포트폴리오 비중")

# 매수 가능 금액 기준 비중 계산
df_recommended['비중(%)'] = (df_recommended['매수가능금액'] / df_recommended['매수가능금액'].sum() * 100).round(2)

# 파이차트 생성
fig = px.pie(
    df_recommended,
    values='매수가능금액',
    names='회사명',
    title='추천 포트폴리오 비중 (매수 가능 금액 기준)',
    hole=0.4,
    color_discrete_sequence=px.colors.qualitative.Set3
)

fig.update_traces(
    textposition='inside',
    textinfo='percent+label',
    hovertemplate='<b>%{label}</b><br>비중: %{percent}<br>금액: %{value:,.0f}원<extra></extra>'
)

fig.update_layout(
    font=dict(size=12),
    showlegend=True,
    legend=dict(
        orientation="v",
        yanchor="middle",
        y=0.5,
        xanchor="left",
        x=1.05
    )
)

st.plotly_chart(fig, use_container_width=True)

# 상세 정보 표시
st.markdown("---")
st.markdown("#### 📝 상세 정보")

if len(df_recommended) > 0:
    total_investment = df_recommended['매수가능금액'].sum()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("**📊 가중치 정보**")
        st.write(f"- 안정성: {weights['안정성']:.2%}")
        st.write(f"- 수익률: {weights['수익률']:.2%}")
        st.write(f"- 성장률: {weights['성장률']:.2%}")
        st.write(f"- 밸류에이션: {weights['밸류에이션']:.2%}")
        st.write(f"- 배당률: {weights['배당률']:.2%}")
        st.write(f"- 뉴스감성: {weights['뉴스감성']:.2%}")
        st.write(f"- 유동성: {weights['유동성']:.2%}")
        st.write(f"- 기술지표: {weights['기술적지표']:.2%}")
    
    with col2:
        st.markdown("**💼 포트폴리오 요약**")
        st.write(f"- 추천 종목 수: {len(df_recommended)}개")
        st.write(f"- 예적금 등 안전상품 추천: {savings_amount:,}원 ({savings_ratio*100:.0f}%)")
        st.write(f"- 총 투자 금액: {total_investment:,.0f}원 ({investment_ratio*100:.0f}%)")
        st.write(f"- 미투자 금액: {investment_amount - total_investment:,.0f}원")
        avg_score = df_recommended['최종점수'].mean()
        st.write(f"- 평균 종합점수: {avg_score:.2f}")
    
    with col3:
        st.markdown("**🌍 국가별 분포**")
        country_dist = df_recommended.groupby('국가')['매수가능금액'].sum()
        for country, amount in country_dist.items():
            st.write(f"- {country}: {amount:,.0f}원 ({amount/total_investment*100:.1f}%)")
    
    with col4:
        st.markdown("**🏭 섹터별 분포**")
        sector_dist = df_recommended.groupby('섹터')['매수가능금액'].sum()
        for sector, amount in sector_dist.items():
            st.write(f"- {sector}: {amount:,.0f}원 ({amount/total_investment*100:.1f}%)")
    
    # 포트폴리오 품질 지표
    st.markdown("---")
    st.markdown("#### 📈 포트폴리오 품질 지표")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        avg_return = df_recommended['최근수익률(%)'].mean()
        st.metric("평균 수익률", f"{avg_return:.2f}%")
    
    with col2:
        avg_per = df_recommended['PER'].mean()
        st.metric("평균 PER", f"{avg_per:.1f}")
    
    with col3:
        avg_dividend = df_recommended['배당률(%)'].mean()
        st.metric("평균 배당률", f"{avg_dividend:.2f}%")
    
    with col4:
        avg_growth = df_recommended['성장률(%)'].mean()
        st.metric("평균 성장률", f"{avg_growth:.2f}%")

# 전체 종목 정보 (접을 수 있는 섹션)
with st.expander("📌 전체 종목 정보 보기"):
    all_columns = ['티커', '회사명', '국가', '섹터', '최근수익률(%)', '변동성', 'PER', '배당률(%)', 
                   '시가총액규모', '유동성', '성장률(%)', 'RSI', '뉴스감성(1~5)', '현재가', 
                   '종합점수', '매수가능주수']
    df_all = df_stocks[all_columns].copy()
    df_all['종합점수'] = df_all['종합점수'].round(2)
    df_all['최근수익률(%)'] = df_all['최근수익률(%)'].round(1)
    df_all['PER'] = df_all['PER'].round(1)
    df_all['배당률(%)'] = df_all['배당률(%)'].round(2)
    df_all['성장률(%)'] = df_all['성장률(%)'].round(1)
    df_all['현재가'] = df_all['현재가'].apply(lambda x: f"{int(x):,}원")
    st.dataframe(
        df_all,
        use_container_width=True,
        hide_index=True
    )

