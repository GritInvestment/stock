import streamlit as st
import pandas as pd
import sqlite3
import datetime
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi
from youtubesearchpython import CustomSearch, VideoSortOrder

# --- 페이지 설정 ---
st.set_page_config(page_title="💰 100억 투자 비서", page_icon="📈", layout="wide")

DB_NAME = 'stock_v2.db' 

# --- DB 초기화 ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS experts (id INTEGER PRIMARY KEY, name TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS analysis 
                 (id INTEGER PRIMARY KEY, date TEXT, expert_name TEXT, video_title TEXT, video_url TEXT,
                  market_view TEXT, macro_view TEXT, buy_recom TEXT, sell_recom TEXT)''')
    
    c.execute("SELECT COUNT(*) FROM experts")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO experts (name) VALUES ('김영익')")
        
    conn.commit()
    conn.close()

init_db()

# --- 유튜브 검색 로직 ---
def search_recent_videos(expert_name, max_results=30):
    videos = []
    try:
        customSearch = CustomSearch(f"{expert_name} 주식", VideoSortOrder.uploadDate, limit=max_results)
        results = customSearch.result().get('result', [])
        
        for entry in results:
            if entry and entry.get('link'):
                videos.append({
                    'title': entry.get('title'),
                    'url': entry.get('link')
                })
    except Exception as e:
        st.error(f"영상 검색 중 오류 발생: {e}")
    return videos

# --- AI 분석 로직 (에러 상세 반환으로 업그레이드) ---
def analyze_video_with_gemini(video_url, expert_name, api_key):
    try:
        # 1. 안전한 Video ID 추출 (Shorts, youtu.be 등 다양한 포맷 완벽 대응)
        video_id = ""
        if "v=" in video_url:
            video_id = video_url.split("v=")[-1].split("&")[0]
        elif "youtu.be/" in video_url:
            video_id = video_url.split("youtu.be/")[-1].split("?")[0]
        elif "shorts/" in video_url:
            video_id = video_url.split("shorts/")[-1].split("?")[0]
        else:
            return "지원하지 않는 유튜브 링크 형식입니다."

        # 2. 자막 추출 (더 강력한 로직)
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = transcript_list.find_transcript(['ko']) # 한국어 자막 찾기
            transcript_data = transcript.fetch()
            transcript_text = " ".join([t['text'] for t in transcript_data])
        except Exception:
            return "영상에 한국어 자막(CC)이 없거나 라이브 스트리밍 영상입니다."
            
        transcript_text = transcript_text[:15000] # 토큰 제한 방지

        # 3. 구글 Gemini API 호출
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
    except Exception as e:
        return f"AI 분석 실패 (API 키를 확인해주세요): {str(e)}"

# --- UI 및 메인 로직 ---
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

if selected_expert:
    st.title(f"📈 '{selected_expert}' 인사이트 타임라인")
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🔄 최근 출연 영상 30개 분석 (초기 세팅용)", use_container_width=True):
            if not google_api_key:
                st.error("좌측 상단에 Google API Key를 입력해야 실행됩니다.")
            else:
                with st.spinner(f'{selected_expert}님의 최근 영상을 수집 중입니다...'):
                    videos = search_recent_videos(selected_expert, max_results=30)
                    
                    if not videos:
                        st.warning("영상을 찾지 못했습니다.")
                    else:
                        st.info(f"총 {len(videos)}개의 영상을 찾았습니다. 분석을 시작합니다.")
                        progress_bar = st.progress(0)
                        success_count = 0
                        
                        for i, video in enumerate(videos):
                            # 이미 분석된 영상인지 확인
                            c.execute("SELECT id FROM analysis WHERE video_url=?", (video['url'],))
                            if c.fetchone() is not None:
                                st.toast(f"⏩ 이미 저장된 영상 패스: {video['title'][:20]}...")
                            else:
                                result = analyze_video_with_gemini(video['url'], selected_expert, google_api_key)
                                
                                # 결과가 딕셔너리면 성공, 문자열이면 실패 사유
                                if isinstance(result, dict):
                                    formatted_date = datetime.datetime.now().strftime("%Y-%m-%d")
                                    c.execute('''INSERT INTO analysis (date, expert_name, video_title, video_url, market_view, macro_view, buy_recom, sell_recom)
                                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                                              (formatted_date, selected_expert, video['title'], video['url'], 
                                               result["market_view"], result["macro_view"], result["buy_recom"], result["sell_recom"]))
                                    conn.commit()
                                    success_count += 1
                                    st.toast(f"✅ 분석 완료: {video['title'][:20]}...")
                                else:
                                    # 왜 실패했는지 화면 우측 하단에 상세 이유 출력
                                    st.toast(f"❌ 분석 건너뜀 ({result}): {video['title'][:15]}...")
                                    
                            progress_bar.progress((i + 1) / len(videos))
                        st.success(f"✅ 작업 완료! 총 {success_count}개의 새로운 인사이트가 저장되었습니다.")

    # 매일 업데이트용 버튼 로직도 위와 동일하게 방어 로직 적용
    with col2:
        if st.button("▶️ 오늘 새 영상 확인하기", type="primary", use_container_width=True):
            if not google_api_key:
                st.error("좌측 상단에 Google API Key를 입력해야 실행됩니다.")
            else:
                with st.spinner('새로운 인터뷰 영상을 확인 중입니다...'):
                    videos = search_recent_videos(selected_expert, max_results=5) 
                    
                    if not videos:
                        st.warning("영상을 찾지 못했습니다.")
                    else:
                        new_found = False
                        for video in videos:
                            c.execute("SELECT id FROM analysis WHERE video_url=?", (video['url'],))
                            if c.fetchone() is None:
                                result = analyze_video_with_gemini(video['url'], selected_expert, google_api_key)
                                if isinstance(result, dict):
                                    new_found = True
                                    formatted_date = datetime.datetime.now().strftime("%Y-%m-%d")
                                    c.execute('''INSERT INTO analysis (date, expert_name, video_title, video_url, market_view, macro_view, buy_recom, sell_recom)
                                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                                              (formatted_date, selected_expert, video['title'], video['url'], 
                                               result["market_view"], result["macro_view"], result["buy_recom"], result["sell_recom"]))
                                    conn.commit()
                                else:
                                    st.toast(f"❌ 분석 건너뜀 ({result}): {video['title'][:15]}...")
                        if new_found:
                            st.success("✅ 새로운 영상 분석 완료!")
                        else:
                            st.info("새롭게 분석할 만한 영상이 없습니다.")

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