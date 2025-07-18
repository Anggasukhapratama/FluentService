import os
from datetime import timedelta

# JWT Configuration
JWT_SECRET_KEY = os.environ.get('JWT_SECRET', 'fluentendpoint')
JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
API_SECRET_KEY = os.environ.get('API_KEY', 'fluentendpoint')
GOOGLE_CLIENT_ID_WEB = os.environ.get('GOOGLE_CLIENT_ID_WEB', '757791586393-5jci80p25u6s81j1atbem043gitsegm7.apps.googleusercontent.com')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'AIzaSyCthUsqHnex60K8J-IIvsAq9oNGH5ko3dk') 

# Forgot password / Mail Configuration
MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USE_SSL = False
MAIL_USERNAME = os.environ.get('EMAIL_USER', 'edigitaldompet@gmail.com')
MAIL_PASSWORD = os.environ.get('EMAIL_PASS', 'jyag nujw fwki njdl')
MAIL_DEFAULT_SENDER = ('Fluent', MAIL_USERNAME)

# MongoDB Connection String
MONGO_URI = "mongodb://localhost:27017/"

# HRD Questions Database (Existing)
hrd_question_details = {
    "Ceritakan pengalaman kerja Anda yang paling menantang": {
        "keywords": ["tantangan", "solusi", "belajar", "mengatasi", "proyek"],
        "ideal_length": 20
    },
    "Apa kelebihan dan kekurangan Anda?": {
        "keywords": ["kelebihan", "kekuatan", "kekurangan", "kelemahan", "mengembangkan"],
        "ideal_length": 15
    },
    "Mengapa kami harus mempekerjakan Anda?": {
        "keywords": ["kontribusi", "skill", "cocok", "nilai", "perusahaan"],
        "ideal_length": 18
    },
    "Apa motivasi Anda bekerja di perusahaan ini?": {
        "keywords": ["motivasi", "visi", "misi", "budaya", "perusahaan"],
        "ideal_length": 15
    },
    "Bagaimana Anda menghadapi tekanan di tempat kerja?": {
        "keywords": ["tekanan", "manajemen stres", "prioritas", "tenang", "solusi"],
        "ideal_length": 16
    },
    "Apa pencapaian terbesar Anda dalam karier?": {
        "keywords": ["pencapaian", "hasil", "usaha", "proyek", "target"],
        "ideal_length": 17
    },
    "Bagaimana Anda bekerja dalam tim?": {
        "keywords": ["kerja sama", "tim", "komunikasi", "kontribusi", "kolaborasi"],
        "ideal_length": 15
    },
    "Apa yang Anda ketahui tentang perusahaan ini?": {
        "keywords": ["informasi", "industri", "produk", "layanan", "nilai"],
        "ideal_length": 14
    },
    "Apa rencana karier Anda ke depan?": {
        "keywords": ["rencana", "karier", "tujuan", "pengembangan", "masa depan"],
        "ideal_length": 16
    },
    "Bagaimana Anda mengatasi konflik di tempat kerja?": {
        "keywords": ["konflik", "komunikasi", "solusi", "tenang", "kerja sama"],
        "ideal_length": 18
    },
    "Apakah Anda bersedia bekerja lembur atau di bawah tekanan?": {
        "keywords": ["komitmen", "fleksibilitas", "lembur", "dedikasi", "tanggung jawab"],
        "ideal_length": 14
    },
    "Apa yang Anda lakukan jika tidak setuju dengan atasan?": {
        "keywords": ["pendapat", "komunikasi", "respek", "diskusi", "solusi"],
        "ideal_length": 15
    },
    "Apa nilai-nilai kerja yang Anda pegang teguh?": {
        "keywords": ["integritas", "komitmen", "disiplin", "tanggung jawab", "etika"],
        "ideal_length": 14
    },
    "Bagaimana Anda menetapkan prioritas dalam pekerjaan?": {
        "keywords": ["prioritas", "manajemen waktu", "deadline", "efisiensi", "fokus"],
        "ideal_length": 15
    },
    "Apa alasan Anda ingin meninggalkan pekerjaan sebelumnya?": {
        "keywords": ["pengembangan", "tantangan baru", "karier", "motivasi", "tujuan"],
        "ideal_length": 16
    }
}

hrd_questions_list = list(hrd_question_details.keys())

# ======================== NEW: INTERVIEW TOPICS FOR GEMINI ========================
INTERVIEW_TOPICS = {
    "general": {
        "name": "Umum (Perkenalan Diri, motivasi)",
        "prompt_context": "Anda adalah seorang pewawancara HRD profesional. Fokus pada pertanyaan umum tentang latar belakang kandidat, motivasi, dan kesesuaian budaya kerja. Buat pertanyaan pembuka yang baik dan relevan.",
        "keywords": ["perkenalan", "diri", "motivasi", "bekerja", "kelebihan", "kekurangan", "visi", "misi"],
    },
    "technical_web_developer": {
        "name": "Teknis - Web Developer",
        "prompt_context": "Anda adalah pewawancara teknis untuk posisi Web Developer. Tanyakan tentang pengalaman dengan HTML, CSS, JavaScript, framework (React/Angular/Vue), backend (Node.js/Python/PHP), database (SQL/NoSQL), dan Git.",
        "keywords": ["HTML", "CSS", "JavaScript", "React", "Node.js", "Python", "SQL", "Git", "API", "framework"],
    },
    "technical_data_analyst": {
        "name": "Teknis - Data Analyst",
        "prompt_context": "Anda adalah pewawancara teknis untuk posisi Data Analyst. Tanyakan tentang keahlian dalam SQL, Python/R, Excel, statistik, visualisasi data, data cleaning, dan pemecahan masalah data.",
        "keywords": ["SQL", "Python", "R", "Excel", "statistik", "visualisasi", "data cleaning", "big data", "analisis"],
    },
    "entrepreneurship": {
        "name": "Kewirausahaan",
        "prompt_context": "Anda adalah seorang investor dan pewawancara yang mencari talenta kewirausahaan. Tanyakan tentang ide bisnis, manajemen risiko, inovasi, kepemimpinan, dan adaptasi terhadap pasar.",
        "keywords": ["bisnis", "inovasi", "startup", "resiko", "pemimpin", "pasar", "modal", "strategi", "tim"],
    },
    "leadership": {
        "name": "Kepemimpinan",
        "prompt_context": "Anda adalah pewawancara yang menilai potensi kepemimpinan. Tanyakan tentang pengalaman memimpin tim, mengambil keputusan sulit, memotivasi bawahan, dan menyelesaikan konflik internal.",
        "keywords": ["kepemimpinan", "tim", "keputusan", "motivasi", "konflik", "delegasi", "visi", "mentoring"],
    },
    "problem_solving": {
        "name": "Pemecahan Masalah",
        "prompt_context": "Anda adalah pewawancara yang fokus pada kemampuan pemecahan masalah. Berikan skenario atau tanyakan pengalaman mereka dalam mengidentifikasi masalah, menganalisis akar penyebab, dan menerapkan solusi efektif.",
        "keywords": ["masalah", "solusi", "analisis", "logika", "inovatif", "strategi", "data"],
    },
}