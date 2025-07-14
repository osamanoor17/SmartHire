from __future__ import annotations
import urllib.parse
import base64, email, io, os, re, textwrap, tempfile
from pathlib import Path
from typing import List, Tuple
import streamlit as st
from dotenv import load_dotenv
import google.generativeai as genai
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from pdfminer.high_level import extract_text as extract_text_from_pdf
from docx import Document
from pymongo import MongoClient
import plotly.express as px
from cryptography.fernet import Fernet

print(Fernet.generate_key().decode())

# ---------------------------------------------------------
# 1. ENV & API CONFIG
# ---------------------------------------------------------
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

if not GOOGLE_API_KEY:
    st.error("❌ GOOGLE_API_KEY missing in .env file.")
    st.stop()

if not MONGO_URI:
    st.error("❌ MONGO_URI missing in .env file.")
    st.stop()

genai.configure(api_key=GOOGLE_API_KEY)

client = MongoClient(MONGO_URI)
db = client["smart_hire"]
jd_collection = db["job_descriptions"]
resumes_collection = db["resumes"]

GMAIL_QUERY = os.getenv("GMAIL_QUERY", "label:CVs")
GMAIL_SCOPES = os.getenv("GMAIL_SCOPES", "https://www.googleapis.com/auth/gmail.readonly").split(",")
CREDENTIALS_FILE = Path("credentials.json")
TOKEN_FILE = Path(tempfile.gettempdir()) / "smart_hire_token.json"

# ---------------------------------------------------------
# 2. MongoDB Functions
# ---------------------------------------------------------
def save_job_description(title: str, description: str):
    jd_collection.insert_one({"title": title, "description": description})

def get_all_job_descriptions():
    return list(jd_collection.find({}, {"_id": 0}))

def save_resume(filename: str, content: str):
    resumes_collection.insert_one({"filename": filename, "content": content})


# ---------------------------------------------------------
# 3. GMAIL INTEGRATION
# ---------------------------------------------------------
def get_gmail_service() -> "build":
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                st.error("❌ credentials.json not found.")
                st.stop()
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    # Fetch logged-in email and store in session
    profile = service.users().getProfile(userId="me").execute()
    st.session_state.gmail_logged_in = True
    st.session_state.gmail_email = profile.get("emailAddress", "")
    return service


def fetch_resumes_from_gmail(query: str = GMAIL_QUERY) -> List[Tuple[str, bytes]]:
    service = get_gmail_service()
    resumes = []
    seen_filenames = set()

    try:
        search = service.users().messages().list(userId="me", q=query).execute()
        message_ids = search.get("messages", [])

        for msg in message_ids:
            msg_detail = service.users().messages().get(userId="me", id=msg["id"]).execute()
            payload = msg_detail.get("payload", {})
            parts = payload.get("parts", [])

            for part in parts:
                filename = part.get("filename")
                mime_type = part.get("mimeType", "")

                if filename in seen_filenames:
                    continue

                if filename and re.match(r"application/(pdf|vnd\\.openxml.*|msword)", mime_type):
                    att_id = part["body"].get("attachmentId")
                    if not att_id:
                        continue

                    att = service.users().messages().attachments().get(
                        userId="me", messageId=msg["id"], id=att_id).execute()

                    file_data = base64.urlsafe_b64decode(att["data"])
                    resumes.append((filename, file_data))
                    seen_filenames.add(filename)

    except HttpError as err:
        st.error(f"📬 Gmail API error: {err}")

    return resumes


# ---------------------------------------------------------
# 4. TEXT EXTRACTION
# ---------------------------------------------------------
def extract_text_from_bytes(filename: str, file_bytes: bytes) -> str | None:
    name = filename.lower()
    try:
        if name.endswith(".pdf"):
            return extract_text_from_pdf(io.BytesIO(file_bytes))
        elif name.endswith((".doc", ".docx")):
            doc = Document(io.BytesIO(file_bytes))
            return "\n".join(p.text for p in doc.paragraphs)
        elif name.endswith(".txt"):
            return file_bytes.decode("utf-8", errors="ignore")
    except Exception as exc:
        st.warning(f"❌ Could not extract text from {filename}: {exc}")
    return None


# ---------------------------------------------------------
# 5. GEMINI LOGIC
# ---------------------------------------------------------
def gemini_chat(parts: List[str] | str) -> str:
    content = parts if isinstance(parts, list) else [parts]
    model = genai.GenerativeModel("gemini-1.5-flash")
    try:
        resp = model.generate_content(content)
        return resp.text
    except Exception as exc:
        return f"⚠️ Gemini error: {exc}"


SHORTLIST_PROMPT = textwrap.dedent("""\
You are a hiring assistant.
Decide whether to **Shortlist** or **Reject** the candidate.
Respond with only one word – Shortlist or Reject – and one sentence reason.

Job Description:
{jd}

Resume:
{cv}
""")


def shortlist_decision(jd: str, resume: str) -> str:
    return gemini_chat(SHORTLIST_PROMPT.format(jd=jd, cv=resume[:8000]))


def is_relevant_resume(jd: str, resume: str) -> bool:
    prompt = SHORTLIST_PROMPT.format(jd=jd, cv=resume[:8000])
    decision = gemini_chat(prompt)
    return "Shortlist" in decision


eval_prompt = "Evaluate the resume vs job description. Mention strengths, weaknesses, and overall fit."
match_prompt = "Give match percentage (0-100%), missing keywords, and summary."
interview_prompt = "Generate 5 interview questions based on this resume and job description:\n\n{cv}"


def generate_interview_questions(resume: str) -> str:
    return gemini_chat(interview_prompt.format(cv=resume[:8000]))

# ---------------------------------------------------------
# 6. JOB RECOMMENDATION LINKS
# ---------------------------------------------------------
def generate_job_search_links(resume_text: str, job_description: str):
    prompt = f"""
    From the following job description and resume, extract the best-fit job title and 3-5 relevant keywords or skills to search jobs online.

    Job Description:
    {job_description}

    Resume:
    {resume_text[:2000]}
    """
    response = gemini_chat(prompt)
    st.session_state["job_search_summary"] = response
    search_query = response.replace("\n", " ").strip()
    encoded = urllib.parse.quote(search_query)

    return {
        "LinkedIn Jobs": f"https://www.linkedin.com/jobs/search/?keywords={encoded}",
        "Indeed": f"https://www.indeed.com/jobs?q={encoded}",
        "Glassdoor": f"https://www.glassdoor.com/Job/jobs.htm?sc.keyword={encoded}"
    }

# ---------------------------------------------------------
# 7. UI SETUP
# ---------------------------------------------------------
st.set_page_config("SmartHire – AI Recruiter", "🤖", layout="wide")

if "gmail_logged_in" not in st.session_state:
    st.session_state.gmail_logged_in = False
if "gmail_email" not in st.session_state:
    st.session_state.gmail_email = ""

st.markdown("""
<style>
.stApp {
    background: linear-gradient(to right, #89f7fe, #66a6ff);3db54b



    background-attachment: fixed;
    color: black;
}
section[data-testid="stSidebar"] {
    background: linear-gradient(to bottom,  #66a6ff,#1e9ce2);
    color: black;
}
.resume-box {
    background-color: rgba(255, 255, 255, 0.1);
    padding: 16px;
    border-radius: 10px;
    max-height: 400px;
    overflow-y: auto;
    font-size: 15px;
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.1);
}
.stButton>button {
    background-color: #243b55;
    color: white;
    font-weight: bold;
    border-radius: 8px;
    border: none;
}
.stButton>button:hover {
    background-color: #e3f2fd;
    color: black;
}
.stTextInput>div>div>input,
.stTextArea>div>textarea {
    background-color: #e3f2fd;
    color: black;
    border-radius: 5px;
}
h1, h2, h3, h4 {
    color: #ffffff;
}
::-webkit-scrollbar {
    width: 8px;
}
::-webkit-scrollbar-thumb {
    background: #90caf9;
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 8. MAIN APP INTERFACE START
# ---------------------------------------------------------
st.title("🤖 SmartHire – AI-Powered Recruiter")

# --- Sidebar ---
with st.sidebar:
    st.header("📧 Gmail Login")

    if st.session_state.gmail_logged_in:
        st.success(f"Logged in as {st.session_state.gmail_email}")
        if st.button("🚪 Logout"):
            if TOKEN_FILE.exists():
                TOKEN_FILE.unlink()
            st.session_state.gmail_logged_in = False
            st.session_state.gmail_email = ""
            st.success("✅ Logged out successfully.")
            st.stop()
    else:
        if st.button("🔐 Login with Gmail"):
            with st.spinner("🔗 Connecting to Gmail..."):
                get_gmail_service()
            st.rerun()

    st.divider()
    st.header("➕ Add Job Description")

    if "jd_title" not in st.session_state:
        st.session_state.jd_title = ""
    if "jd_input" not in st.session_state:
        st.session_state.jd_input = ""

    st.session_state.jd_title = st.text_input("Job Title", value=st.session_state.jd_title)
    st.session_state.jd_input = st.text_area("Job Description", value=st.session_state.jd_input)

    if st.button("💾 Save JD"):
        if st.session_state.jd_title and st.session_state.jd_input:
            save_job_description(st.session_state.jd_title, st.session_state.jd_input)
            st.success(f"✅ JD '{st.session_state.jd_title}' saved to MongoDB.")
            st.session_state.jd_title = ""
            st.session_state.jd_input = ""
        else:
            st.warning("❗ Title and Description are required.")

    st.divider()
    if not st.session_state.gmail_logged_in:
        st.info("🔐 Please login to Gmail first.")
    else:
        if st.button("🔍 Fetch Relevant CVs"):
            if not st.session_state.get("job_description"):
                st.warning("⚠️ Select job description first.")
            else:
                all_resumes = fetch_resumes_from_gmail(GMAIL_QUERY)
                st.write(f"📄 {len(all_resumes)} total attachments found.")
                filtered_resumes = []
                shortlisted_count = 0
                rejected_count = 0

                with st.spinner("📬 Filtering resumes using Gemini..."):
                    for i, (name, file_bytes) in enumerate(all_resumes, 1):
                        st.write(f"🔎 Checking resume {i}: {name}")
                        resume_text = extract_text_from_bytes(name, file_bytes)
                        if not resume_text:
                            st.warning(f"⚠️ Could not extract text from {name}")
                            continue

                        try:
                            if is_relevant_resume(st.session_state["job_description"], resume_text):
                                filtered_resumes.append((name, file_bytes))
                                shortlisted_count += 1
                                save_resume(name, resume_text)
                                st.success(f"✅ {name} shortlisted")
                            else:
                                rejected_count += 1
                                st.info(f"❌ {name} rejected")
                        except Exception as e:
                            st.error(f"Gemini Error on {name}: {e}")

                st.session_state["resumes"] = filtered_resumes
                st.success(f"🎯 Found {len(filtered_resumes)} relevant resume(s)")

                if shortlisted_count + rejected_count > 0:
                    st.markdown("### 📊 Resume Shortlisting Summary")
                    chart_data = {
                        "Status": ["Shortlisted", "Rejected"],
                        "Count": [shortlisted_count, rejected_count]
                    }
                    fig = px.pie(chart_data, names="Status", values="Count", title="CV Shortlisting Distribution")
                    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------
# 9. MAIN CONTENT: JD SELECTOR & RESUME ACTIONS
# ---------------------------------------------------------
st.subheader("📂 Select Job Description")
jds = get_all_job_descriptions()
jd_titles = [jd["title"] for jd in jds]
selected_title = st.selectbox("Select Job Title", jd_titles)

job_description = next((jd["description"] for jd in jds if jd["title"] == selected_title), "")
st.text_area("Job Description", job_description, height=200, disabled=True)
st.session_state["job_description"] = job_description
resumes = st.session_state.get("resumes", [])

# ---------------------------------------------------------
# 10. RESUME VIEWER + ACTIONS
# ---------------------------------------------------------
if resumes:
    st.divider()
    st.subheader("📂 Resumes")
    selected = st.selectbox("Select Resume", [f"{i+1}. {name}" for i, (name, _) in enumerate(resumes)])
    idx = int(selected.split(".")[0]) - 1
    filename, file_bytes = resumes[idx]
    resume_text = extract_text_from_bytes(filename, file_bytes)

    if not resume_text:
        st.error("❌ Could not extract resume text.")
    else:
        st.markdown("#### 📄 Resume Preview")
        st.markdown(f"<div class='resume-box'>{resume_text[:2000]}</div>", unsafe_allow_html=True)

        st.divider()
        st.markdown("### 🔍 Choose Action")
        action = st.selectbox("Choose action", [
            "Shortlist Decision",
            "Evaluate Resume",
            "Match Percentage",
            "Generate Interview Questions",
            "Show Job Suggestions"
        ])

        if st.button("▶️ Run"):
            if not job_description.strip():
                st.warning("⚠️ Please select a job description to proceed.")
            else:
                with st.spinner("⏳ Processing..."):
                    if action == "Shortlist Decision":
                        result = shortlist_decision(job_description, resume_text)
                        st.markdown("### 🛂 Shortlist Decision")
                        st.info(result)

                    elif action == "Evaluate Resume":
                        combined = f"Job Description:\n{job_description}\n\nResume:\n{resume_text}"
                        st.markdown("### 📋 Evaluation")
                        st.write(gemini_chat([combined, eval_prompt]))

                    elif action == "Match Percentage":
                        combined = f"Job Description:\n{job_description}\n\nResume:\n{resume_text}"
                        st.markdown("### 📊 Match Result")
                        st.write(gemini_chat([combined, match_prompt]))

                    elif action == "Generate Interview Questions":
                        st.markdown("### 🎯 Interview Questions")
                        st.write(generate_interview_questions(resume_text))

                    elif action == "Show Job Suggestions":
                        st.markdown("### 🔗 Job Suggestions")
                        links = generate_job_search_links(resume_text, job_description)
                        st.markdown(f"**Search Query Used:** {st.session_state.get('job_search_summary', '')}")
                        for site, url in links.items():
                            st.markdown(f"[🔍 View Jobs on {site}]({url})", unsafe_allow_html=True)
else:
    st.info("📭 No resumes loaded. Fetch from Gmail using the sidebar.")

# ---------------------------------------------------------
# 11. FEEDBACK SECTION
# ---------------------------------------------------------
st.divider()
with st.expander("💬 Feedback"):
    feedback = st.text_area("Your feedback")
    if st.button("Submit Feedback"):
        st.success("Thanks for your feedback!")
