import streamlit as st
import pandas as pd
import sqlite3
import datetime
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi

# --- 페이지 설정 (모바일 친화적) ---
st.set_page_config(page_title="💰 100억 투자 비서", page_icon="📈", layout="centered")

# --- DB 초기화 ---
def init_db():
    conn = sqlite3.connect('stock_mobile_insights.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS analysis 
                 (id INTEGER PRIMARY KEY, date TEXT, expert_name TEXT, 
                  market_view TEXT, macro_view TEXT, buy_recom TEXT, sell_recom TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 사이드바: 설정 및 구글 API 키 입력 ---
with st.sidebar:
    st.header("⚙️ 시스템 설정")
    google_api_key = st.text_input("Google Gemini API Key", type="password", help="구글 AI 스튜디오에서 발급받은 키를 입력하세요.")
    st.markdown("---")
    st.markdown("### 👥 전문가 관리")
    expert_name_input = st.text_input("새 전문가 이름")
    if st.button("전문가 추가"):
        st.success(f"{expert_name_input} 추가 완료! (UI 예시)")

# --- 메인 화면 ---
st.title("📈 오늘의 투자 인사이트")
st.caption("구글 Gemini AI가 요약한 핵심 리포트입니다.")

# --- AI 분석 로직 (Gemini API 연동) ---
def analyze_video_with_gemini(video_url, expert_name):
    if not google_api_key:
        st.error("좌측 상단(모바일은 > 버튼) 설정에서 Google API Key를 먼저 입력해주세요.")
        return None
        
    try:
        # 1. 유튜브 자막 추출 (예시: 영상 ID만 파싱하는 로직 필요. 여기서는 임시 텍스트)
        # video_id = video_url.split("v=")[1]
        # transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko'])
        # transcript_text = " ".join([t['text'] for t in transcript_list])
        transcript_text = "하반기 금리는 내려갈 것이고, 반도체 장비주를 유심히 보세요. 바이오는 지금 너무 비쌉니다." # 가상 스크립트

        # 2. 구글 Gemini API 설정 및 호출
        genai.configure(api_key=google_api_key)
        # 최신 고성능 모델 적용 (Gemini 1.5 Flash가 빠르고 저렴하여 요약에 적합)
        model = genai.GenerativeModel('gemini-1.5-flash') 
        
        prompt = f"""
        당신은 100억 자산가를 위한 수석 투자 비서입니다. 
        다음은 주식 전문가 '{expert_name}'의 유튜브 영상 스크립트입니다. 
        이 내용을 바탕으로 다음 4가지 항목을 각각 1~2줄로 명확하게 요약해 주세요. 
        결과는 [증시 시황], [매크로 전망], [매수 추천], [매도 추천] 이라는 키워드를 포함한 텍스트로 주세요.
        
        스크립트: {transcript_text}
        """
        
        response = model.generate_content(prompt)
        
        # 실제 환경에서는 응답 텍스트를 파싱하여 딕셔너리로 만듭니다. (여기서는 간략화)
        return {
            "date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "expert_name": expert_name,
            "market_view": "박스권 상단 돌파 시도 중 (AI 요약)",
            "macro_view": "하반기 금리 인하 기대감 유효 (AI 요약)",
            "buy_recom": "반도체 장비주 (AI 요약)",
            "sell_recom": "단기 고평가 바이오 (AI 요약)"
        }
    except Exception as e:
        st.error(f"분석 중 오류 발생: {e}")
        return None

# --- 분석 실행 섹션 ---
st.markdown("### ▶️ 새로운 영상 분석")
col1, col2 = st.columns([3, 1])
with col1:
    video_url = st.text_input("유튜브 영상 링크", placeholder="https://youtube.com/...")
with col2:
    selected_expert = st.selectbox("전문가", ["슈퍼개미 김철수", "여의도 박이사"])

if st.button("AI 자동 분석 실행", use_container_width=True, type="primary"):
    with st.spinner('구글 Gemini가 영상을 분석 중입니다...'):
        result = analyze_video_with_gemini(video_url, selected_expert)
        if result:
            conn = sqlite3.connect('stock_mobile_insights.db')
            c = conn.cursor()
            c.execute('''INSERT INTO analysis (date, expert_name, market_view, macro_view, buy_recom, sell_recom)
                         VALUES (?, ?, ?, ?, ?, ?)''', 
                      (result["date"], result["expert_name"], result["market_view"], 
                       result["macro_view"], result["buy_recom"], result["sell_recom"]))
            conn.commit()
            conn.close()
            st.success("✅ 분석 및 저장 완료!")

# --- 저장된 데이터 조회 (모바일 친화적 카드형 UI) ---
st.markdown("### 📋 누적 인사이트 리포트")
conn = sqlite3.connect('stock_mobile_insights.db')
df = pd.read_sql_query("SELECT * FROM analysis ORDER BY date DESC", conn)
conn.close()

if not df.empty:
    for index, row in df.iterrows():
        with st.expander(f"📅 {row['date']} | 👤 {row['expert_name']}"):
            st.markdown(f"**🌍 매크로 전망:** {row['macro_view']}")
            st.markdown(f"**📊 증시 시황:** {row['market_view']}")
            st.markdown(f"**🔴 매수 추천:** {row['buy_recom']}")
            st.markdown(f"**🔵 매도 추천:** {row['sell_recom']}")
else:
    st.info("아직 분석된 데이터가 없습니다.")

# --- 엑셀 다운로드 기능 ---
if not df.empty:
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 전체 데이터 엑셀(CSV) 다운로드",
        data=csv,
        file_name='stock_insights.csv',
        mime='text/csv',
        use_container_width=True
    )