import streamlit as st
import requests
import time

# n8n Webhook URL
N8N_URL = "https://jerusha.app.n8n.cloud/webhook/1d0fcbfc-b568-408d-b4a9-ab278307a79f"

st.set_page_config(page_title="n8n 챗봇", page_icon="🤖")
st.title("🤖 n8n Webhook 기반 챗봇 (스트리밍 + Markdown)")

# 세션 상태 초기화
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
    
if "streaming_pos" not in st.session_state:
    st.session_state.streaming_pos = {}  # 각 메시지의 현재 스트리밍 위치

# 사이드바 설정
with st.sidebar:
    st.header("⚙️ 설정")
    streaming_speed = st.slider("스트리밍 속도", 0.001, 0.05, 0.01, 0.001, 
                                 help="값이 작을수록 빠릅니다 (초 단위)")
    
    if st.button("🔄 대화 초기화"):
        st.session_state.chat_history = []
        st.session_state.streaming_pos = {}
        st.rerun()

user_input = st.chat_input("메시지를 입력하세요")

if user_input:
    # 사용자 메시지 추가
    st.session_state.chat_history.append(("user", user_input))
    
    # Webhook 호출
    with st.spinner("답변을 생성하는 중..."):
        try:
            params = {"chatInput": user_input, "sessionId": "abc"}
            r = requests.get(N8N_URL, params=params, timeout=60)
            data = r.json()

            if "output" in data:
                bot_reply = data["output"]
            else:
                bot_reply = f"⚠️ 응답에 'output' 키가 없습니다.\n\n받은 데이터: {data}"

        except Exception as e:
            bot_reply = f"❌ 오류 발생: {e}"

    # 봇 응답 추가 (스트리밍 시작)
    msg_idx = len(st.session_state.chat_history)
    st.session_state.chat_history.append(("bot", bot_reply))
    st.session_state.streaming_pos[msg_idx] = 0  # 스트리밍 시작 위치
    st.rerun()

# UI 렌더링
streaming_active = False

for idx, (role, msg) in enumerate(st.session_state.chat_history):
    if role == "user":
        with st.chat_message("user"):
            st.markdown(msg)
    else:
        with st.chat_message("assistant"):
            # 스트리밍 상태 확인
            current_pos = st.session_state.streaming_pos.get(idx, -1)
            
            # 스트리밍이 진행 중인 경우
            if current_pos >= 0 and current_pos < len(msg):
                # 현재 위치까지의 텍스트 표시
                display_text = msg[:current_pos + 1]
                container = st.empty()
                container.markdown(display_text)
                
                # 다음 글자로 진행 (한 번에 여러 글자 처리하여 성능 개선)
                chars_per_frame = max(1, int(1 / (streaming_speed * 100)))  # 프레임당 글자 수
                next_pos = min(current_pos + chars_per_frame, len(msg))
                st.session_state.streaming_pos[idx] = next_pos
                streaming_active = True
            else:
                # 스트리밍 완료된 메시지는 전체 표시
                st.markdown(msg)

# 스트리밍이 진행 중이면 짧은 딜레이 후 다시 렌더링
if streaming_active:
    time.sleep(streaming_speed)
    st.rerun()
