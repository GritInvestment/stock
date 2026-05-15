import streamlit as st
import pandas as pd
import sqlite3
import datetime
import os
import time  # ⭐️ 시간 텀을 주기 위한 부품 추가
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi
from youtubesearchpython import CustomSearch, VideoSortOrder
import yt_dlp

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
def search_recent_videos(expert_name, max_results=5): # 기본 검색량을 30개에서 5개로 축소
    videos = []
    try:
        customSearch = CustomSearch(f"{expert_name} 주식", VideoSortOrder.uploadDate, limit=max_results)
        results = customSearch.result().get('result', [])
        for entry in results:
            if entry and entry.get('link'):
                videos.append({'title': entry.get('title'), 'url': entry.get('link')})
    except Exception as e:
        st.error(f"영상 검색 중 오류 발생: {e}")
    return videos

# --- AI 분석 로직 (403 우회 유지) ---
def analyze_video_with_gemini(video_url, expert_name, api_key):
    try:
        video_id = ""
        if "v=" in video_url:
            video_id = video_url.split("v=")[-1].split("&")[0]
        elif "youtu.be/" in video_url:
            video_id = video_url.split("youtu.be/")[-1].split("?")[0]
        elif "shorts/" in video_url:
            video_id = video_url.split("shorts/")[-1].split("?")[0]
        else:
            return "지원하지 않는 영상 링크입니다."

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash') 
        
        prompt = f"""
        당신은 100억 자산가를 위한 수석 투자 비서입니다. 
        다음은 주식 전문가 '{expert_name}'이(가) 출연한 유튜브 영상의 내용입니다. 
        이 내용을 바탕으로 다음 4가지 항목을 각각 1~2줄로 요약해 주세요. 
        결과는 반드시 아래의 포맷을 지켜서 출력하세요.

        [증시 시황] 내용
        [매크로 전망] 내용
        [매수 추천] 내용
        [매도 추천] 내용
        """

        transcript_text = None

        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko'])
            transcript_text = " ".join([t['text'] for t in transcript_list])
            if len(transcript_text) < 100:
                transcript_text = None 
            else:
                transcript_text = transcript_text[:15000]
        except Exception:
            pass 

        if transcript_text:
            full_prompt = prompt + f"\n\n스크립트: {transcript_text}"
            response = model.generate_content(full_prompt)
        else:
            # 안드로이드 모바일 기기로 위장
            ydl_opts = {
                'format': 'm4a/bestaudio/worst', 
                'outtmpl': f'{video_id}.%(ext)s',
                'quiet': True,
                'noplaylist': True,
                'extractor_args': {'youtube': ['player_client=android,ios,web']} 
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                ext = info.get('ext', 'm4a')
                audio_filename = f"{video_id}.{ext}"

            try:
                uploaded_file = genai.upload_file(path=audio_filename)
                response = model.generate_content([prompt, uploaded_file])
                genai.delete_file(uploaded_file.name)
            finally:
                if os.path.exists(audio_filename):
                    os.remove(audio_filename)

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
        return f"분석 오류 (오디오 처리 실패 또는 API 초과): {str(e)}"

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
    st.caption("🤖 차단 우회 중: 사람이 직접 보는 것처럼 5개씩 천천히 스캔합니다.")
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    col1, col2 = st.columns([1, 1])
    with col1:
        # 대표님 의견 반영: 30개에서 5개로 변경
        if st.button("🔄 최근 영상 5개 분석 (천천히 수집)", use_container_width=True):
            if not google_api_key:
                st.error("좌측 상단에 Google API Key를 입력해야 실행됩니다.")
            else:
                with st.spinner(f'영상을 1개씩 천천히 수집하고 분석 중입니다...'):
                    videos = search_recent_videos(selected_expert, max_results=5)
                    
                    if not videos:
                        st.warning("영상을 찾지 못했습니다.")
                    else:
                        progress_bar = st.progress(0)
                        success_count = 0
                        error_logs = [] 
                        
                        for i, video in enumerate(videos):
                            c.execute("SELECT id FROM analysis WHERE video_url=?", (video['url'],))
                            if c.fetchone() is not None:
                                pass 
                            else:
                                st.toast(f"진행 중: {video['title'][:15]}...")
                                result = analyze_video_with_gemini(video['url'], selected_expert, google_api_key)
                                
                                if isinstance(result, dict):
                                    formatted_date = datetime.datetime.now().strftime("%Y-%m-%d")
                                    c.execute('''INSERT INTO analysis (date, expert_name, video_title, video_url, market_view, macro_view, buy_recom, sell_recom)
                                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                                              (formatted_date, selected_expert, video['title'], video['url'], 
                                               result["market_view"], result["macro_view"], result["buy_recom"], result["sell_recom"]))
                                    conn.commit()
                                    success_count += 1
                                else:
                                    error_logs.append(f"[{video['title'][:30]}...] ❌ 사유: {result}")
                                
                                # ⭐️ 대표님 아이디어 적용: 영상 하나 분석 후 5초간 대기 (유튜브 감시망 회피) ⭐️
                                time.sleep(5)
                                    
                            progress_bar.progress((i + 1) / len(videos))
                        
                        if success_count > 0:
                            st.success(f"✅ 작업 완료! 총 {success_count}개의 새로운 인사이트가 저장되었습니다.")
                        else:
                            st.warning("작업 완료! 새로운 인사이트가 저장되지 않았습니다.")
                        
                        if error_logs:
                            with st.expander(f"⚠️ 영상 분석 실패 내역 보기"):
                                for err in error_logs:
                                    st.write(err)

    with col2:
        if st.button("▶️ 오늘 새 영상 확인하기 (매일 업데이트용)", type="primary", use_container_width=True):
            if not google_api_key:
                st.error("좌측 상단에 Google API Key를 입력해야 실행됩니다.")
            else:
                with st.spinner('새로운 인터뷰 영상을 천천히 확인 중입니다...'):
                    videos = search_recent_videos(selected_expert, max_results=5) 
                    
                    if not videos:
                        st.warning("영상을 찾지 못했습니다.")
                    else:
                        new_found = False
                        error_logs = []
                        
                        for video in videos:
                            c.execute("SELECT id FROM analysis WHERE video_url=?", (video['url'],))
                            if c.fetchone() is None:
                                st.toast(f"진행 중: {video['title'][:15]}...")
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
                                    error_logs.append(f"[{video['title'][:30]}...] ❌ 사유: {result}")
                                
                                # ⭐️ 여기서도 5초 대기 적용 ⭐️
                                time.sleep(5)
                        
                        if new_found:
                            st.success("✅ 새로운 영상 분석 완료!")
                        else:
                            st.info("새롭게 분석할 만한 영상이 없습니다.")
                            
                        if error_logs:
                            with st.expander(f"⚠️ 실패 내역 보기"):
                                for err in error_logs:
                                    st.write(err)

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