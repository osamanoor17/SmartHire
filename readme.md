# 🤖 SmartHire – AI-Powered Resume Screener

**SmartHire** is a smart, AI-powered resume screening app that automates the tedious recruitment process. It fetches resumes directly from Gmail, extracts their content, analyzes them using Google Gemini, and helps recruiters shortlist the most suitable candidates — all from an intuitive Streamlit dashboard.

---

## 📌 Features

- 📥 **Fetch Resumes from Gmail** (PDF, DOCX, TXT attachments)
- 🧠 **AI-Powered Resume Evaluation** via Google Gemini 1.5 Flash
- 📊 **Shortlist or Reject** decisions with reasoning
- 📋 **Strengths, Weaknesses & Match Summary**
- 🎯 **Interview Question Generator**
- 🔍 **Job Recommendation Links** (LinkedIn, Glassdoor, Indeed)
- 💾 **MongoDB Integration** for storing job descriptions and resumes
- 🎨 **Modern UI** built with Streamlit and Plotly

---

## 🖼️ Demo


![SmartHire UI](https://youtu.be/y6ij_e4VDdA?si=n0TukrwHsXMKbySW)

---

## 🔧 Tech Stack

| Tool/Library           | Purpose                                   |
|------------------------|-------------------------------------------|
| **Streamlit**          | Frontend & UI rendering                   |
| **Google Gemini API**  | AI-powered resume understanding           |
| **Gmail API**          | Fetching attachments from Gmail           |
| **MongoDB (Atlas)**    | Database for job descriptions and resumes |
| **pdfminer.six**       | Extract text from PDF files               |
| **python-docx**        | Extract text from DOCX files              |
| **dotenv**             | Manage environment variables              |
| **cryptography**       | Encrypt/decrypt sensitive data            |
| **Plotly**             | Interactive charts                        |

---

## 📁 Folder Structure

```
├── ai_recruiter_app.py # Main Streamlit app
├── requirements.txt # Python dependencies
├── credentials.json # Gmail OAuth client credentials (keep secret)
├── .env # Environment variables (never push to GitHub)
├── .streamlit/
│ └── config.toml # Streamlit UI config (optional)
└── README.md
```
## ⚙️ Getting Started (Local Setup)

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/smarthire-ai.git
cd smarthire-ai
```

### 2. Create a Virtual Environment
Bash (Linux/macOS/Git Bash):
```
python -m venv venv
source venv/bin/activate
```
Windows CMD:
```
python -m venv venv
venv\Scripts\activate
```
### 3. Install Required Packages
```
pip install -r requirements.txt
```
### 4. Setup .env File
Create a file named .env in the root directory and add:
```
GOOGLE_API_KEY=your_google_gemini_api_key
MONGO_URI=mongodb+srv://<username>:<password>@<cluster-url>/smart_hire?retryWrites=true&w=majority
GMAIL_QUERY=label:CVs
GMAIL_SCOPES=https://www.googleapis.com/auth/gmail.readonly
```
### 5. Add Google Credentials
Save your Gmail OAuth credentials as:
```
credentials.json
```
⚠️ Do not share this file publicly.

### 6. Run the App
```
streamlit run app.py
```

### 🚀 Deployment Guide (Streamlit Cloud)
1. Push your code to GitHub

2. Go to Streamlit Cloud

3. Click "New App"

4. Choose your repo and select app.py

5. Go to Secrets tab and add the following:
```
GOOGLE_API_KEY = your_google_gemini_api_key
MONGO_URI = mongodb+srv://...
GMAIL_QUERY = label:CVs
GMAIL_SCOPES = https://www.googleapis.com/auth/gmail.readonly
GOOGLE_CLIENT_SECRET = """
<contents of credentials.json>
"""
```
### 📦 Required Packages
```
streamlit
google-auth
google-auth-oauthlib
google-auth-httplib2
google-api-python-client
python-dotenv
pdfminer.six
python-docx
pymongo
cryptography
plotly
google-generativeai
```
### 📜 License
This project is licensed under the MIT License.
Feel free to use, modify, and distribute with attribution.