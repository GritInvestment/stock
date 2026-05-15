import streamlit as st
import pandas as pd
import sqlite3
import datetime
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp

# --- 페이지 설정 ---
st.set_page_config(page_title="💰 100억 투자 비서", page_icon="📈", layout="wide")

# ★ 핵심 해결 부분: DB 이름을 stock_v2.db 로 변경하여 기존 충돌을 무시합니다 ★
DB_NAME = 'stock_v2.db' 

# --- DB 초기화 ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # 전문가 테이블
    c.execute('''CREATE TABLE IF NOT EXISTS experts (id INTEGER PRIMARY KEY, name TEXT UNIQUE)''')
    # 분석 결과 테이블
    c.execute('''CREATE TABLE IF NOT EXISTS analysis 
                 (id INTEGER PRIMARY KEY, date TEXT, expert_name TEXT, video_title TEXT, video_url TEXT,
                  market_view TEXT, macro_view TEXT, buy_recom TEXT, sell_recom TEXT)''')
    
    c.execute("SELECT COUNT(*) FROM experts")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO experts (name) VALUES ('김영익')")
        
    conn.commit()
    conn.close()

init_db()

# --- 유튜브 전체 최신 검색 로직 (yt-dlp) ---
def search_recent_videos(expert_name, max_results=30):
    search_query = f"ytsearchdate{max_results}:\"{expert_name} 주식\""
    ydl_opts = {'extract_flat': True, 'quiet': True, 'ignoreerrors': True}
    videos = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=False)
            if 'entries' in info:
                for entry in info['entries']:
                    if entry: 
                        videos.append({
                            'title': entry.get('title'),
                            'url': entry.get('url'),
                            'date': entry.get('upload_date')
                        })
    except Exception as e:
        st.error(f"영상 검색 중 오류 발생: {e}")
    return videos

# --- AI 분석 로직 ---
def analyze_video_with_gemini(video_url, expert_name, api_key):
    try:
        video_id = video_url.split("v=")[-1].split("&")[0]
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko'])
        transcript_text = " ".join([t['text'] for t in transcript_list])
        transcript_text = transcript_text[:15000]

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash') 
        
        prompt = f"""
        당신은 100억 자산가를 위한 수석 투자 비서입니다. 
        다음은 주식 전문가 '{expert_name}'이(가) 출연한 유튜브 영상 스크립트입니다. 
        이 내용을 바탕으로 다음 4가지 항목을 각각 1~2줄로 요약해 주세요. 
        결과는 반드시 아래의 포맷을 지켜서 출력하세요.

        [증시 시황] 내용
        [매크로 전망] 내용
        [매수 추천] 내용
        [매도 추천] 내용
        
        스크립트: {transcript_text}
        """
        
        response = model.generate_content(prompt)
        text = response.text
        
        def extract_section(keyword):
            if f"[{keyword}]" in text:
                return text.split(f"[{keyword}]")[1].split("[")[0].strip()
            return "언급 없음"

        return {
            "market_view": extract_section("증시 시황"),
            "macro_view": extract_section("매크로 전망"),
            "buy_recom": extract_section("매수 추천"),
            "sell_recom": extract_section("매도 추천")
        }
    except Exception:
        return None

# --- 사이드바: 설정 및 전문가 목록 ---
with st.sidebar:
    st.header("⚙️ 시스템 설정")
    google_api_key = st.text_input("Google API Key 입력", type="password")
    
    st.markdown("---")
    st.header("👥 관심 전문가")
    
    conn = sqlite3.connect(DB_NAME)
    experts_df = pd.read_sql_query("SELECT * FROM experts", conn)
    expert_names = experts_df['name'].tolist()
    
    selected_expert = st.radio("전문가를 선택하세요", expert_names) if expert_names else None
    
    st.markdown("---")
    st.markdown("### ➕ 전문가 추가")
    with st.form("add_expert_form"):
        new_name = st.text_input("이름 (예: 박세익, 강영현 등)")
        submit_btn = st.form_submit_button("추가하기")
        if submit_btn and new_name:
            try:
                c = conn.cursor()
                c.execute("INSERT INTO experts (name) VALUES (?)", (new_name.strip(),))
                conn.commit()
                st.success("추가 완료! 우측 상단 'Rerun' 또는 새로고침을 눌러주세요.")
            except sqlite3.IntegrityError:
                st.error("이미 등록된 전문가입니다.")
    conn.close()

# --- 메인 화면 ---
if selected_expert:
    st.title(f"📈 '{selected_expert}' 인사이트 타임라인")
    st.caption(f"어느 채널에 출연하셨든 {selected_expert}님의 가장 최근 인터뷰를 찾아 요약합니다.")
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🔄 최근 출연 영상 30개 싹 모아서 분석 (초기 세팅용)", use_container_width=True):
            if not google_api_key:
                st.error("좌측 상단에 Google API Key를 입력해야 실행됩니다.")
            else:
                with st.spinner(f'유튜브 전체에서 {selected_expert}님의 최근 영상 30개를 찾아 분석 중입니다...'):
                    videos = search_recent_videos(selected_expert, max_results=30)
                    progress_bar = st.progress(0)
                    
                    success_count = 0
                    for i, video in enumerate(videos):
                        c.execute("SELECT id FROM analysis WHERE video_url=?", (video['url'],))
                        if c.fetchone() is None:
                            result = analyze_video_with_gemini(video['url'], selected_expert, google_api_key)
                            if result:
                                formatted_date = f"{video['date'][:4]}-{video['date'][4:6]}-{video['date'][6:]}" if video['date'] else datetime.datetime.now().strftime("%Y-%m-%d")
                                c.execute('''INSERT INTO analysis (date, expert_name, video_title, video_url, market_view, macro_view, buy_recom, sell_recom)
                                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                                          (formatted_date, selected_expert, video['title'], video['url'], 
                                           result["market_view"], result["macro_view"], result["buy_recom"], result["sell_recom"]))
                                conn.commit()
                                success_count += 1
                        progress_bar.progress((i + 1) / len(videos))
                    st.success(f"✅ 분석 완료! 총 {success_count}개의 새로운 인사이트가 저장되었습니다.")

    with col2:
        if st.button("▶️ 오늘 새로 출연하신 영상 찾기 (매일 업데이트용)", type="primary", use_container_width=True):
            if not google_api_key:
                st.error("좌측 상단에 Google API Key를 입력해야 실행됩니다.")
            else:
                with st.spinner('새로운 인터뷰 영상이 있는지 확인 중입니다...'):
                    videos = search_recent_videos(selected_expert, max_results=5) 
                    new_found = False
                    for video in videos:
                        c.execute("SELECT id FROM analysis WHERE video_url=?", (video['url'],))
                        if c.fetchone() is None:
                            result = analyze_video_with_gemini(video['url'], selected_expert, google_api_key)
                            if result:
                                new_found = True
                                formatted_date = f"{video['date'][:4]}-{video['date'][4:6]}-{video['date'][6:]}" if video['date'] else datetime.datetime.now().strftime("%Y-%m-%d")
                                c.execute('''INSERT INTO analysis (date, expert_name, video_title, video_url, market_view, macro_view, buy_recom, sell_recom)
                                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                                          (formatted_date, selected_expert, video['title'], video['url'], 
                                           result["market_view"], result["macro_view"], result["buy_recom"], result["sell_recom"]))
                                conn.commit()
                    if new_found:
                        st.success("✅ 새로운 영상 분석 완료! 하단에 추가되었습니다.")
                    else:
                        st.info("아직 새롭게 출연하신 영상이 없습니다.")

    st.markdown("---")
    
    df = pd.read_sql_query("SELECT * FROM analysis WHERE expert_name=? ORDER BY date DESC", conn, params=(selected_expert,))
    conn.close()

    if not df.empty:
        for index, row in df.iterrows():
            with st.expander(f"📅 {row['date']} | 📺 {row['video_title']}"):
                st.markdown(f"**🌍 매크로 전망:** {row['macro_view']}")
                st.markdown(f"**📊 증시 시황:** {row['market_view']}")
                st.markdown(f"**🔴 매수 추천:** {row['buy_recom']}")
                st.markdown(f"**🔵 매도 추천:** {row['sell_recom']}")
                st.markdown(f"[원본 유튜브 영상 보러가기]({row['video_url']})")
    else:
        st.info("아직 수집된 데이터가 없습니다. 상단의 버튼을 눌러 초기 세팅을 진행해 주세요.")
else:
    st.info("👈 좌측에서 관심 있는 전문가를 먼저 추가해 주세요.")