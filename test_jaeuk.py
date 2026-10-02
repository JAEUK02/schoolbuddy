import os
import io
import json
import boto3
import psycopg2
import requests
import streamlit as st
import google.generativeai as genai
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# LangChain 및 AWS 연동
from langchain_aws import BedrockEmbeddings
from notice_helpers import (
    database_cursor, ingest_notice, recent_analysis_objects,
    translated_notice_or_original, validate_notice,
)

load_dotenv()

# --- [1] 서비스 및 보안 설정 ---
# API 키는 환경 변수에서만 읽습니다.
GENAI_API_KEY = os.getenv("GENAI_API_KEY")
if not GENAI_API_KEY:
    st.error("GENAI_API_KEY 환경 변수를 설정한 뒤 앱을 실행하세요.")
    st.stop()
genai.configure(api_key=GENAI_API_KEY)
MODEL_NAME = 'models/gemini-2.5-flash'

@st.cache_resource
def init_aws():
    region = "us-west-2" 
    bedrock = boto3.client("bedrock-runtime", region_name=region)
    s3 = boto3.client('s3', region_name=region)
    return bedrock, s3

@st.cache_resource
def get_embeddings_model():
    bedrock, _ = init_aws()
    return BedrockEmbeddings(client=bedrock, model_id="amazon.titan-embed-text-v1")

def get_db_conn():
    try:
        return psycopg2.connect(
            host=os.getenv('DB_HOST'), database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'),
            port='5432', connect_timeout=3
        )
    except Exception:
        return None

bedrock, s3 = init_aws()

# --- [2] 핵심 유틸리티 함수 ---

# ✨ 실시간 내용 번역 (캐싱 적용으로 속도와 성능 최적화)
@st.cache_data(show_spinner=False, ttl=3600)
def translate_content(raw_json_str, target_lang):
    """S3 원본 JSON을 읽어와 사용자가 선택한 언어로 즉석 번역 및 캐싱합니다."""
    original = validate_notice(raw_json_str)
    if target_lang == "한국어 (Korean)":
        return original
    
    prompt = f"""
    You are a professional JSON translation engine. 
    Translate the following JSON string into {target_lang}.
    Rules:
    - Translate ONLY the string values.
    - Preserve the original JSON structure and all keys ('title', 'summary', 'details') exactly.
    - Return valid JSON ONLY.
    
    JSON:
    {json.dumps(original, ensure_ascii=False)}
    """
    try:
        model = genai.GenerativeModel(
            MODEL_NAME,
            generation_config={"response_mime_type": "application/json"}
        )
        response = model.generate_content(prompt)
        return translated_notice_or_original(original, response.text)
    except Exception:
        return original

def log_interaction(title, link):
    conn = get_db_conn()
    if conn:
        try:
            with database_cursor(conn, commit=True) as cur:
                cur.execute(
                    "INSERT INTO program_logs (user_lang, program_title, program_link) VALUES (%s, %s, %s)",
                    (st.session_state.language, title, link)
                )
        except Exception:
            pass


def extract_notice_text(file_bytes, file_name):
    file_ext = file_name.rsplit('.', 1)[-1].lower()
    if file_ext in ['jpg', 'jpeg', 'png']:
        model = genai.GenerativeModel(MODEL_NAME)
        image_part = {"mime_type": f"image/{file_ext.replace('jpg', 'jpeg')}", "data": file_bytes}
        prompt = "이 이미지에 포함된 모든 텍스트를 한국어로 정확히 읽어서 텍스트만 출력해줘."
        return model.generate_content([prompt, image_part]).text
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    return "".join(page.extract_text() or "" for page in reader.pages)


def analyze_notice_text(text):
    model = genai.GenerativeModel(MODEL_NAME)
    prompt = f"Analyze notice. Respond in JSON ONLY. Fields: title, summary, details:{{date: 'YYYY-MM-DD'}}. Content: {text[:3000]}"
    response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
    return response.text

@st.cache_data(ttl=3600)
def fetch_external_programs():
    url = "https://www.liveinkorea.kr/web/lay1/bbs/S1T10C27/A/4/list.do"
    programs = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        items = soup.select(".tbl_type1_wrap dl.tbl_list_type1")
        for dl in items[:6]:
            title_tag = dl.select_one("dt a span.title")
            link_tag = dl.select_one("dt a")
            if title_tag and link_tag:
                title = title_tag.get_text(strip=True)
                href = link_tag.get('href', '')
                link = "https://www.liveinkorea.kr/web/lay1/bbs/S1T10C27/A/4/" + href
                date = "N/A"
                date_items = dl.select("dd ul.date_search li")
                if len(date_items) >= 2: date = date_items[1].get_text(strip=True)
                programs.append({"title": title, "link": link, "date": date})
        return programs
    except Exception:
        return []

# --- [3] UI/UX 설정 ---
st.set_page_config(page_title="School Buddy", page_icon="🎒", layout="wide")

if 'language' not in st.session_state: st.session_state.language = '한국어 (Korean)'

lang_pack = {
    "한국어 (Korean)": {
        "title": "🏠 학교 소식 대시보드", "monitor_h3": "AI 가정통신문 분석", "monitor_p": "최근 소식을 확인하세요.",
        "status": "작동중", "date": "날짜", "sidebar_upload": "새 공지 등록", "upload_label": "PDF/이미지 선택",
        "chat_placeholder": "학교 생활에 대해 물어보세요...", "btn_analyze": "🚀 분석 및 DB 저장",
        "menu_program": "🌟 맞춤 프로그램 추천", "prog_desc": "다누리 지원센터의 최신 프로그램을 추천해 드립니다.",
        "no_data": "등록된 공지가 없습니다. 새 공지를 업로드해 주세요."
    },
    "English": {
        "title": "🏠 News Dashboard", "monitor_h3": "AI Document Analysis", "monitor_p": "Check recent updates.",
        "status": "Active", "date": "Date", "sidebar_upload": "Upload Notice", "upload_label": "Select PDF/Image",
        "chat_placeholder": "Ask about school life...", "btn_analyze": "🚀 Analyze & Save",
        "menu_program": "🌟 Program Recommendations", "prog_desc": "Latest programs from Danuri Center.",
        "no_data": "No notices yet. Upload a notice to get started."
    },
    "Tiếng Việt": {
        "title": "🏠 Bảng tin nhà trường", "monitor_h3": "Phân tích AI", "monitor_p": "Kiểm tra cập nhật mới nhất.",
        "status": "Đang hoạt động", "date": "Ngày", "sidebar_upload": "Đăng ký thông báo", "upload_label": "Chọn PDF/Hình ảnh",
        "chat_placeholder": "Hỏi về cuộc sống học đường...", "btn_analyze": "🚀 Phân tích & Lưu",
        "menu_program": "🌟 Đề xuất chương trình", "prog_desc": "Các chương trình mới nhất từ Trung tâm Danuri.",
        "no_data": "Chưa có thông báo. Hãy tải thông báo lên để bắt đầu."
    },
    "中文": {
        "title": "🏠 学校仪表판", "monitor_h3": "AI 通信 분석", "monitor_p": "查看最新更新。",
        "status": "运行中", "date": "日期", "sidebar_upload": "注册通知", "upload_label": "选择 PDF/图像",
        "chat_placeholder": "询问学校생활...", "btn_analyze": "🚀 분석 및 DB 저장",
        "menu_program": "🌟 项目 추천", "prog_desc": "来自 Danuri 中심의 최신 프로젝트 추천.",
        "no_data": "暂无通知。请上传通知以开始使用。"
    }
}
curr_lang = lang_pack.get(st.session_state.language, lang_pack["한국어 (Korean)"])

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; background-color: #0E1117 !important; color: #E0E0E0 !important; }
[data-testid="stSidebar"] { background-color: #161B22 !important; border-right: 1px solid #30363D !important; }
.notice-card { background-color: #1D1D1F !important; border-radius: 16px; padding: 1.5rem; margin-bottom: 1.2rem; border-left: 5px solid #FF9800; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
.mcp-monitor { background: rgba(46, 125, 50, 0.1); border-radius: 16px; padding: 1.2rem; display: flex; align-items: center; gap: 1rem; border: 1px solid #2E7D32; margin-bottom: 1.5rem; }
</style>
""", unsafe_allow_html=True)

if 'messages' not in st.session_state: st.session_state.messages = []
if 'current_page' not in st.session_state: st.session_state.current_page = 'dashboard'

# --- [4] 사이드바 및 업로드 로직 ---
with st.sidebar:
    st.markdown("<div style='text-align: center;'><h1>🎒</h1><h2>School Buddy</h2></div>", unsafe_allow_html=True)
    selected_lang = st.selectbox("🌐 Language", options=list(lang_pack.keys()), index=list(lang_pack.keys()).index(st.session_state.language))
    if selected_lang != st.session_state.language:
        st.session_state.language = selected_lang
        st.rerun()
    
    st.markdown("---")
    if st.button("🏠 Dashboard", use_container_width=True): st.session_state.current_page = 'dashboard'
    if st.button("💬 AI Chat", use_container_width=True): st.session_state.current_page = 'chat'
    if st.button(f"{curr_lang['menu_program']}", use_container_width=True): st.session_state.current_page = 'programs'
    
    st.markdown("---")
    uploaded_file = st.file_uploader(curr_lang['upload_label'], type=['pdf', 'jpg', 'png', 'jpeg'], label_visibility="collapsed")
    
    if st.button(curr_lang['btn_analyze'], use_container_width=True, type="primary"):
        if uploaded_file:
            with st.spinner("이미지/PDF 분석 및 지식 베이스 등록 중..."):
                result = ingest_notice(
                    s3=s3, bucket=os.getenv('BUCKET_NAME'),
                    file_bytes=uploaded_file.getvalue(), file_name=uploaded_file.name,
                    extract_text=extract_notice_text, analyze_text=analyze_notice_text,
                    connect=get_db_conn, embeddings_factory=get_embeddings_model,
                )
                if result.raw_saved:
                    st.info("원본 파일 S3 저장 완료.")
                if result.summary_saved:
                    st.info("분석 요약 S3 저장 완료.")
                if result.indexed:
                    st.success("✅ 분석 및 지식 베이스 등록 완료!")
                    st.rerun()
                elif result.summary_saved:
                    st.warning("요약은 저장됐지만 지식 베이스 등록은 완료되지 않았습니다. DB 연결과 설정을 확인하세요.")
                elif result.error_code == "no_text":
                    st.error("텍스트를 추출할 수 없습니다. 파일 상태를 확인하세요.")
                elif result.error_code == "invalid_notice":
                    st.error("분석 결과가 유효한 공지 JSON이 아닙니다. 요약과 지식 베이스는 저장하지 않았습니다.")
                else:
                    st.error("공지 처리 중 오류가 발생했습니다. 저장된 원본은 자동 삭제하지 않습니다.")

# --- [5] 메인 화면 로직 ---

# A. 대시보드 (실시간 번역 및 카드형 UI)
if st.session_state.current_page == 'dashboard':
    st.title(curr_lang["title"])
    st.markdown(f'<div class="mcp-monitor">🔍 <b>{curr_lang["monitor_h3"]}</b>: {curr_lang["monitor_p"]} <span style="margin-left:auto;">● {curr_lang["status"]}</span></div>', unsafe_allow_html=True)
    
    try:
        response = s3.list_objects_v2(Bucket=os.getenv('BUCKET_NAME'), Prefix='analysis/')
        sorted_files = recent_analysis_objects(response)
        if sorted_files:
            
            for obj in sorted_files[:3]:
                file_obj = s3.get_object(Bucket=os.getenv('BUCKET_NAME'), Key=obj['Key'])
                raw_json_str = file_obj['Body'].read().decode('utf-8')
                
                # 실시간 번역 적용
                data = translate_content(raw_json_str, st.session_state.language)
                
                st.markdown(f"""
                <div class="notice-card">
                    <h4>📄 {data.get('title')}</h4>
                    <p>{data.get('summary')}</p>
                    <div style="font-size:0.85rem; color:#86868B;">📅 {curr_lang['date']}: <b>{data['details'].get('date') or '—'}</b></div>
                </div>
                """, unsafe_allow_html=True)
        else: st.info(curr_lang["no_data"])
    except Exception as e: st.error(f"S3 데이터 로드 오류: {e}")

# B. AI 채팅 (벡터 검색 기반 RAG)
elif st.session_state.current_page == 'chat':
    st.title("💬 AI Chat")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
    if query := st.chat_input(curr_lang['chat_placeholder']):
        st.session_state.messages.append({"role": "user", "content": query})
        with st.chat_message("user"): st.markdown(query)
        with st.chat_message("assistant"):
            with st.spinner("정보를 분석 중..."):
                embeddings_model = get_embeddings_model()
                query_vector = embeddings_model.embed_query(query)
                conn = get_db_conn()
                context_text = ""
                if conn:
                    with database_cursor(conn) as cur:
                        cur.execute("SELECT content FROM documents ORDER BY embedding <-> %s::vector LIMIT 10", (query_vector,))
                        context_text = "\n\n".join([r[0] for r in cur.fetchall()])
                
                model = genai.GenerativeModel(MODEL_NAME)
                # 공지사항 원본 데이터를 바탕으로 한 답변 생성
                prompt = f"Answer in {st.session_state.language}. [Notice Context]:\n{context_text}\n\nQuestion: {query}"
                resp = model.generate_content(prompt)
                st.markdown(resp.text)
                st.session_state.messages.append({"role": "assistant", "content": resp.text})
                st.rerun()

# C. 맞춤 프로그램 추천 (크롤링 데이터 통합)
elif st.session_state.current_page == 'programs':
    st.title(curr_lang['menu_program'])
    st.markdown(f"#### {curr_lang['prog_desc']}")
    programs = fetch_external_programs()
    if programs:
        for idx, pg in enumerate(programs):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f'<div class="program-card"><b>{pg["title"]}</b><br><small>📅 {pg["date"]}</small></div>', unsafe_allow_html=True)
            with col2:
                if st.button("🔗 이동", key=f"pg_{idx}", use_container_width=True):
                    log_interaction(pg['title'], pg['link'])
                    st.components.v1.html(f"<script>window.open('{pg['link']}')</script>", height=0)
            st.markdown("<br>", unsafe_allow_html=True)

st.markdown("<br><hr><p style='text-align:center; color:#86868B; font-size:0.8rem;'>© 2026 School Buddy | Integrated Intelligence v1.0</p>", unsafe_allow_html=True)
