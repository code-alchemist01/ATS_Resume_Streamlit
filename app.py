import streamlit as st
import requests
import json
import PyPDF2
import docx
from io import BytesIO
import re
from typing import Dict, List, Tuple
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
import datetime
import uuid
import hashlib

# Sayfa konfigürasyonu
st.set_page_config(
    page_title="ATS Resume Analyzer Pro",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

class DatabaseManager:
    def __init__(self):
        self.connection_string = "host=localhost port=5432 dbname=atsScore user=postgres password=123456"
        
    def get_connection(self):
        """PostgreSQL bağlantısı oluşturur"""
        try:
            conn = psycopg2.connect(self.connection_string)
            return conn
        except Exception as e:
            st.error(f"Veritabanı bağlantı hatası: {str(e)}")
            return None
    
    def create_tables(self):
        """Gerekli tabloları oluşturur"""
        conn = self.get_connection()
        if not conn:
            return False
            
        try:
            cursor = conn.cursor()
            
            # Resumes tablosu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS resumes (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    title VARCHAR(255) NOT NULL,
                    file_name VARCHAR(255),
                    extracted_text TEXT,
                    content_hash VARCHAR(64) UNIQUE,
                    sector VARCHAR(100),
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # ATS Analyses tablosu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ats_analyses (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    resume_id UUID REFERENCES resumes(id) ON DELETE CASCADE,
                    overall_score INTEGER,
                    contact_score INTEGER,
                    summary_score INTEGER,
                    experience_score INTEGER,
                    education_score INTEGER,
                    skills_score INTEGER,
                    suggestions JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Job Matches tablosu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS job_matches (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    resume_id UUID REFERENCES resumes(id) ON DELETE CASCADE,
                    job_title VARCHAR(255),
                    job_description TEXT,
                    compatibility_score INTEGER,
                    missing_skills JSONB,
                    matching_skills JSONB,
                    suggestions JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            conn.commit()
            cursor.close()
            conn.close()
            return True
            
        except Exception as e:
            st.error(f"Tablo oluşturma hatası: {str(e)}")
            if conn:
                conn.close()
            return False
    
    def save_resume(self, title: str, file_name: str, extracted_text: str, sector: str) -> Dict:
        """CV'yi veritabanına kaydeder - duplicate kontrolü ile"""
        # İçerik hash'ini hesapla
        content_hash = self.calculate_content_hash(extracted_text)
        
        # Duplicate kontrolü yap
        duplicate_check = self.check_duplicate_resume(content_hash)
        if duplicate_check["exists"]:
            return {
                "success": False,
                "is_duplicate": True,
                "existing_resume": duplicate_check,
                "resume_id": duplicate_check["resume_id"]
            }
        
        conn = self.get_connection()
        if not conn:
            return {"success": False, "is_duplicate": False, "resume_id": None}
            
        try:
            cursor = conn.cursor()
            resume_id = str(uuid.uuid4())
            
            cursor.execute("""
                INSERT INTO resumes (id, title, file_name, extracted_text, content_hash, sector)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (resume_id, title, file_name, extracted_text, content_hash, sector))
            
            conn.commit()
            cursor.close()
            conn.close()
            return {
                "success": True,
                "is_duplicate": False,
                "resume_id": resume_id
            }
            
        except Exception as e:
            st.error(f"CV kaydetme hatası: {str(e)}")
            if conn:
                conn.close()
            return {"success": False, "is_duplicate": False, "resume_id": None}
    
    def save_ats_analysis(self, resume_id: str, analysis_result: Dict) -> bool:
        """ATS analiz sonucunu kaydeder"""
        conn = self.get_connection()
        if not conn:
            return False
            
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO ats_analyses (
                    resume_id, overall_score, contact_score, summary_score,
                    experience_score, education_score, skills_score, suggestions
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                resume_id,
                analysis_result.get('overall_score', 0),
                analysis_result.get('contact_info', {}).get('score', 0),
                analysis_result.get('professional_summary', {}).get('score', 0),
                analysis_result.get('work_experience', {}).get('score', 0),
                analysis_result.get('education', {}).get('score', 0),
                analysis_result.get('skills', {}).get('score', 0),
                json.dumps(analysis_result, ensure_ascii=False)
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            return True
            
        except Exception as e:
            st.error(f"ATS analiz kaydetme hatası: {str(e)}")
            if conn:
                conn.close()
            return False
    
    def save_job_match(self, resume_id: str, job_title: str, job_description: str, match_result: Dict) -> bool:
        """İş eşleştirme sonucunu kaydeder"""
        conn = self.get_connection()
        if not conn:
            return False
            
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO job_matches (
                    resume_id, job_title, job_description, compatibility_score,
                    missing_skills, matching_skills, suggestions
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                resume_id,
                job_title,
                job_description,
                match_result.get('compatibility_score', 0),
                json.dumps(match_result.get('missing_skills', []), ensure_ascii=False),
                json.dumps(match_result.get('matching_skills', []), ensure_ascii=False),
                json.dumps(match_result, ensure_ascii=False)
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            return True
            
        except Exception as e:
            st.error(f"İş eşleştirme kaydetme hatası: {str(e)}")
            if conn:
                conn.close()
            return False
    
    def get_resume_history(self, limit: int = 10) -> List[Dict]:
        """CV geçmişini getirir"""
        conn = self.get_connection()
        if not conn:
            return []
            
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT r.*, 
                       COUNT(a.id) as analysis_count,
                       COUNT(j.id) as job_match_count
                FROM resumes r
                LEFT JOIN ats_analyses a ON r.id = a.resume_id
                LEFT JOIN job_matches j ON r.id = j.resume_id
                GROUP BY r.id
                ORDER BY r.created_at DESC
                LIMIT %s
            """, (limit,))
            
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            st.error(f"CV geçmişi getirme hatası: {str(e)}")
            if conn:
                conn.close()
            return []
    
    def get_analysis_stats(self) -> Dict:
        """Analiz istatistiklerini getirir"""
        conn = self.get_connection()
        if not conn:
            return {}
            
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Toplam istatistikler
            cursor.execute("""
                SELECT 
                    COUNT(DISTINCT r.id) as total_resumes,
                    COUNT(DISTINCT a.id) as total_analyses,
                    COUNT(DISTINCT j.id) as total_job_matches,
                    AVG(a.overall_score) as avg_ats_score
                FROM resumes r
                LEFT JOIN ats_analyses a ON r.id = a.resume_id
                LEFT JOIN job_matches j ON r.id = j.resume_id
            """)
            
            stats = dict(cursor.fetchone())
            
            # Sektör dağılımı
            cursor.execute("""
                SELECT sector, COUNT(*) as count
                FROM resumes
                WHERE sector IS NOT NULL
                GROUP BY sector
                ORDER BY count DESC
            """)
            
            sector_stats = cursor.fetchall()
            stats['sector_distribution'] = [dict(row) for row in sector_stats]
            
            cursor.close()
            conn.close()
            
            return stats
            
        except Exception as e:
            st.error(f"İstatistik getirme hatası: {str(e)}")
            if conn:
                conn.close()
            return {}
    
    def calculate_content_hash(self, text: str) -> str:
        """CV içeriğinin hash değerini hesaplar"""
        # Metni normalize et (boşlukları ve satır sonlarını temizle)
        normalized_text = re.sub(r'\s+', ' ', text.strip().lower())
        # SHA-256 hash hesapla
        return hashlib.sha256(normalized_text.encode('utf-8')).hexdigest()
    
    def check_duplicate_resume(self, content_hash: str) -> Dict:
        """Aynı hash değerine sahip CV olup olmadığını kontrol eder"""
        conn = self.get_connection()
        if not conn:
            return {"exists": False, "resume_id": None}
            
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT id, title, file_name, created_at 
                FROM resumes 
                WHERE content_hash = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (content_hash,))
            
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if result:
                return {
                    "exists": True, 
                    "resume_id": result['id'],
                    "title": result['title'],
                    "file_name": result['file_name'],
                    "created_at": result['created_at']
                }
            else:
                return {"exists": False, "resume_id": None}
                
        except Exception as e:
            st.error(f"Duplicate kontrol hatası: {str(e)}")
            if conn:
                conn.close()
            return {"exists": False, "resume_id": None}
    
    def get_all_resumes_for_selection(self) -> List[Dict]:
        """Seçim için tüm CV'leri getirir"""
        conn = self.get_connection()
        if not conn:
            return []
            
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT r.id, r.title, r.file_name, r.sector, r.created_at,
                       COUNT(a.id) as analysis_count,
                       COUNT(j.id) as job_match_count
                FROM resumes r
                LEFT JOIN ats_analyses a ON r.id = a.resume_id
                LEFT JOIN job_matches j ON r.id = j.resume_id
                GROUP BY r.id, r.title, r.file_name, r.sector, r.created_at
                ORDER BY r.created_at DESC
            """)
            
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            st.error(f"CV listesi getirme hatası: {str(e)}")
            if conn:
                conn.close()
            return []
    
    def get_resume_by_id(self, resume_id: str) -> Dict:
        """ID'ye göre CV bilgilerini getirir"""
        conn = self.get_connection()
        if not conn:
            return {}
            
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT * FROM resumes WHERE id = %s
            """, (resume_id,))
            
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            return dict(result) if result else {}
            
        except Exception as e:
            st.error(f"CV getirme hatası: {str(e)}")
            if conn:
                conn.close()
            return {}

class ATSAnalyzer:
    def __init__(self, model_url="http://127.0.0.1:1234"):
        self.model_url = model_url
        self.fallback_mode = False
        self.sector_keywords = {
            "teknoloji": {
                "keywords": ["python", "javascript", "java", "react", "node.js", "aws", "docker", "kubernetes", 
                           "api", "database", "sql", "nosql", "git", "agile", "scrum", "devops", "cloud",
                           "machine learning", "ai", "data science", "frontend", "backend", "fullstack"],
                "role_prompt": "Sen 15 yıllık deneyimli bir Teknoloji şirketi CTO'su ve teknik işe alım uzmanısın.",
                "focus_areas": ["teknik beceriler", "proje deneyimi", "teknoloji stack'i", "problem çözme", "kod kalitesi"]
            },
            "finans": {
                "keywords": ["excel", "sql", "finansal analiz", "risk yönetimi", "muhasebe", "bütçe", "raporlama",
                           "bloomberg", "sap", "oracle", "powerbi", "tableau", "vba", "python", "r",
                           "portföy", "yatırım", "kredi", "sigorta", "bankacılık", "mali müşavir"],
                "role_prompt": "Sen 15 yıllık deneyimli bir Finans sektörü HR direktörü ve finansal işe alım uzmanısın.",
                "focus_areas": ["finansal beceriler", "analitik düşünce", "risk değerlendirmesi", "raporlama", "uyumluluk"]
            },
            "sağlık": {
                "keywords": ["hasta", "tedavi", "tıbbi", "sağlık", "hastane", "klinik", "hemşire", "doktor",
                           "ebe", "fizyoterapist", "eczacı", "tıbbi cihaz", "hasta güvenliği", "hijyen",
                           "acil tıp", "ameliyat", "tanı", "ilaç", "rehabilitasyon", "sağlık yönetimi"],
                "role_prompt": "Sen 15 yıllık deneyimli bir Sağlık sektörü İnsan Kaynakları uzmanı ve tıbbi işe alım uzmanısın.",
                "focus_areas": ["tıbbi bilgi", "hasta bakımı", "güvenlik protokolleri", "etik değerler", "iletişim becerileri"]
            },
            "eğitim": {
                "keywords": ["öğretmen", "eğitim", "öğretim", "müfredat", "sınıf yönetimi", "pedagoji",
                           "öğrenci", "okul", "üniversite", "akademik", "araştırma", "yayın", "konferans",
                           "eğitim teknolojisi", "online eğitim", "uzaktan eğitim", "lms", "moodle"],
                "role_prompt": "Sen 15 yıllık deneyimli bir Eğitim sektörü İnsan Kaynakları uzmanı ve akademik işe alım uzmanısın.",
                "focus_areas": ["eğitim becerileri", "öğretim yöntemleri", "öğrenci gelişimi", "akademik başarı", "inovasyonlar"]
            },
            "pazarlama": {
                "keywords": ["pazarlama", "reklam", "sosyal medya", "seo", "sem", "google ads", "facebook ads",
                           "content marketing", "email marketing", "crm", "analytics", "brand", "kampanya",
                           "dijital pazarlama", "influencer", "pr", "halkla ilişkiler", "etkinlik yönetimi"],
                "role_prompt": "Sen 15 yıllık deneyimli bir Pazarlama sektörü İnsan Kaynakları uzmanı ve pazarlama işe alım uzmanısın.",
                "focus_areas": ["yaratıcılık", "analitik düşünce", "dijital beceriler", "iletişim", "trend takibi"]
            },
            "satış": {
                "keywords": ["satış", "müşteri", "hedef", "bayi", "distribütör", "crm", "lead", "prospect",
                           "closing", "negotiation", "b2b", "b2c", "retail", "wholesale", "account management",
                           "business development", "pipeline", "quota", "commission", "territory"],
                "role_prompt": "Sen 15 yıllık deneyimli bir Satış sektörü İnsan Kaynakları uzmanı ve satış işe alım uzmanısın.",
                "focus_areas": ["satış becerileri", "müşteri ilişkileri", "hedef odaklılık", "ikna kabiliyeti", "sonuç odaklılık"]
            },
            "genel": {
                "keywords": [],
                "role_prompt": "Sen 15 yıllık deneyimli bir İnsan Kaynakları uzmanı ve genel işe alım uzmanısın.",
                "focus_areas": ["genel beceriler", "iş deneyimi", "eğitim", "kişisel gelişim", "adaptasyon"]
            }
        }
        
    def detect_sector(self, text: str) -> str:
        """Metin analizi yaparak sektörü tespit eder"""
        text_lower = text.lower()
        sector_scores = {}
        
        for sector, data in self.sector_keywords.items():
            if sector == "genel":
                continue
                
            score = 0
            keywords = data["keywords"]
            
            for keyword in keywords:
                # Tam kelime eşleşmesi için regex kullan
                pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
                matches = len(re.findall(pattern, text_lower))
                score += matches
            
            # Keyword yoğunluğunu hesapla
            if len(keywords) > 0:
                sector_scores[sector] = score / len(keywords)
            else:
                sector_scores[sector] = 0
        
        # En yüksek skora sahip sektörü döndür
        if sector_scores and max(sector_scores.values()) > 0.1:  # Minimum threshold
            return max(sector_scores, key=sector_scores.get)
        else:
            return "genel"
    
    def get_sector_specific_prompt(self, sector: str, analysis_type: str = "ats") -> str:
        """Sektöre özel prompt oluşturur"""
        sector_data = self.sector_keywords.get(sector, self.sector_keywords["genel"])
        role_prompt = sector_data["role_prompt"]
        focus_areas = sector_data["focus_areas"]
        
        if analysis_type == "ats":
            return f"""
            {role_prompt}
            
            Bu sektörde özellikle şu alanlara odaklanarak CV analizi yapacaksın:
            {', '.join(focus_areas)}
            
            Sektör: {sector.upper()}
            
            Analizinde şu kriterleri öncelikle değerlendir:
            1. Sektöre özel anahtar kelimeler
            2. İlgili deneyim ve projeler  
            3. Sektörel sertifikalar ve eğitimler
            4. Teknik/mesleki yetkinlikler
            5. Sektörel trendlere uygunluk
            """
        elif analysis_type == "job_match":
            return f"""
            {role_prompt}
            
            Bu sektörde iş ilanı ile CV uyumluluğunu değerlendirirken şu alanlara özel dikkat et:
            {', '.join(focus_areas)}
            
            Sektör: {sector.upper()}
            
            Değerlendirmende şu kriterleri öncelikle ele al:
            1. Sektöre özel beceri uyumluluğu
            2. Deneyim seviyesi ve kalitesi
            3. Sektörel terminoloji kullanımı
            4. Kariyer progresyonu mantığı
            5. Sektörel beklentilere uygunluk
            """
        
        return role_prompt
    
    def create_chain_of_thought_prompt(self, base_prompt: str, context: str) -> str:
        """Chain-of-Thought prompting tekniği uygular"""
        cot_prompt = f"""
        Lütfen aşağıdaki analizi adım adım düşünerek yap:
        
        ADIM 1: İlk İzlenim
        - CV'yi genel olarak değerlendir
        - Güçlü ve zayıf yönleri belirle
        
        ADIM 2: Detaylı Analiz  
        - Her bölümü ayrı ayrı incele
        - Eksik olan kısımları tespit et
        
        ADIM 3: Sektörel Uygunluk
        - Sektör gereksinimlerine uygunluğu değerlendir
        - Rekabet avantajlarını belirle
        
        ADIM 4: Öneriler
        - Spesifik iyileştirme önerileri sun
        - Öncelik sırası belirle
        
        {base_prompt}
        
        Analiz edilecek içerik:
        {context}
        """
        
        return cot_prompt
    
    def create_few_shot_examples(self, analysis_type: str) -> str:
        """Few-shot learning için örnek analizler sağlar"""
        if analysis_type == "ats":
            return """
            ÖRNEK ANALİZ 1:
            CV: "5 yıl Python deneyimi, Django, Flask, AWS"
            Analiz: Teknik beceriler güçlü, proje detayları eksik, sertifikalar yok
            Skor: 75/100
            
            ÖRNEK ANALİZ 2:  
            CV: "Pazarlama uzmanı, sosyal medya, Google Ads sertifikası"
            Analiz: Sektörel beceriler mevcut, ölçülebilir sonuçlar eksik
            Skor: 68/100
            
            Şimdi verilen CV'yi bu örneklere benzer şekilde analiz et:
            """
        elif analysis_type == "job_match":
            return """
            ÖRNEK EŞLEŞME 1:
            İş İlanı: "Senior Python Developer, 5+ yıl deneyim"
            CV: "7 yıl Python, Django, AWS deneyimi"
            Uyumluluk: %92 - Deneyim ve beceriler tam uyumlu
            
            ÖRNEK EŞLEŞME 2:
            İş İlanı: "Digital Marketing Specialist, Google Ads"  
            CV: "3 yıl pazarlama, Facebook Ads deneyimi"
            Uyumluluk: %65 - Sektör uyumlu, platform farklı
            
            Şimdi verilen iş ilanı ve CV'yi bu örneklere benzer şekilde eşleştir:
            """
        
        return ""
        
    def check_model_health(self) -> Dict:
        """Model sağlık durumunu kontrol eder"""
        try:
            # Basit bir health check
            response = requests.get(
                f"{self.model_url}/health",
                timeout=5
            )
            if response.status_code == 200:
                return {"status": "healthy", "message": "Model aktif ve hazır"}
        except:
            pass
        
        # Alternatif olarak basit bir test mesajı gönder
        try:
            test_payload = {
                "model": "qwen/qwen3-4b-2507",
                "messages": [{"role": "user", "content": "Test"}],
                "max_tokens": 5,
                "temperature": 0.1
            }
            
            response = requests.post(
                f"{self.model_url}/v1/chat/completions",
                headers={"Content-Type": "application/json"},
                json=test_payload,
                timeout=10
            )
            
            if response.status_code == 200:
                return {"status": "healthy", "message": "Model aktif ve hazır"}
            else:
                return {"status": "error", "message": f"Model yanıt vermiyor (HTTP {response.status_code})"}
                
        except requests.exceptions.Timeout:
            return {"status": "timeout", "message": "Model zaman aşımına uğradı"}
        except requests.exceptions.ConnectionError:
            return {"status": "connection_error", "message": "Model bağlantısı kurulamadı - LM Studio çalışıyor mu?"}
        except Exception as e:
            return {"status": "error", "message": f"Model kontrol hatası: {str(e)}"}

    def call_local_model(self, prompt: str, max_tokens: int = 1000) -> str:
        """Lokal Qwen modelini çağırır - gelişmiş retry mekanizması ile"""
        
        # Önce model sağlığını kontrol et
        health_check = self.check_model_health()
        if health_check["status"] != "healthy":
            return f"❌ Model Hatası: {health_check['message']}"
        
        # Retry parametreleri
        max_retries = 3
        base_timeout = 90  # Başlangıç timeout süresi
        
        for attempt in range(max_retries):
            try:
                # Her denemede timeout süresini artır
                current_timeout = base_timeout + (attempt * 30)
                
                payload = {
                    "model": "qwen/qwen3-4b-2507",
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "frequency_penalty": 0.1,
                    "presence_penalty": 0.1,
                    "stop": ["```", "---", "###"]
                }
                
                # Progress indicator için session state kullan
                if 'model_call_progress' not in st.session_state:
                    st.session_state.model_call_progress = f"🔄 Model çağrısı yapılıyor... (Deneme {attempt + 1}/{max_retries})"
                
                response = requests.post(
                    f"{self.model_url}/v1/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    timeout=current_timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    content = content.strip()
                    
                    # Başarılı olduğunda progress state'i temizle
                    if 'model_call_progress' in st.session_state:
                        del st.session_state.model_call_progress
                    
                    return content
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                    if attempt == max_retries - 1:  # Son deneme
                        return f"❌ Model API Hatası: {error_msg}"
                    continue
                    
            except requests.exceptions.Timeout:
                if attempt == max_retries - 1:  # Son deneme
                    return f"⏱️ Model Zaman Aşımı: {current_timeout}s sonra yanıt alınamadı. LM Studio modelinin yüklendiğinden emin olun."
                continue
                
            except requests.exceptions.ConnectionError:
                if attempt == max_retries - 1:  # Son deneme
                    return "🔌 Bağlantı Hatası: LM Studio çalışmıyor veya port 1234'te erişilemiyor. Lütfen LM Studio'yu başlatın ve modeli yükleyin."
                continue
                
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:  # Son deneme
                    return f"🌐 Ağ Hatası: {str(e)}"
                continue
                
            except json.JSONDecodeError:
                if attempt == max_retries - 1:  # Son deneme
                    return "📄 JSON Hatası: Model geçersiz yanıt formatı döndürdü"
                continue
                
            except Exception as e:
                if attempt == max_retries - 1:  # Son deneme
                    return f"❌ Beklenmeyen Hata: {str(e)}"
                continue
        
        return "❌ Tüm denemeler başarısız oldu"
    
    def get_fallback_ats_analysis(self, resume_text: str) -> Dict:
        """Model çalışmadığında demo ATS analizi döndürür"""
        return {
            "overall_score": 75,
            "keyword_score": 70,
            "format_score": 85,
            "experience_score": 80,
            "education_score": 75,
            "skills_score": 85,
            "contact_score": 90,
            "strengths": [
                "📧 İletişim bilgileri eksiksiz",
                "🎯 Anahtar kelimeler mevcut",
                "📄 Düzenli format kullanımı",
                "💼 İş deneyimi detaylı"
            ],
            "improvements": [
                "🔍 Daha fazla sektörel anahtar kelime ekleyin",
                "📊 Başarı metrikleri ve sayısal veriler ekleyin",
                "🎓 Sertifikalar ve eğitimler vurgulayın",
                "💡 Teknik beceriler bölümünü genişletin"
            ],
            "recommendations": [
                "CV'nizde ölçülebilir başarılar vurgulayın",
                "Sektörel anahtar kelimeleri artırın",
                "Proje deneyimlerinizi detaylandırın",
                "Teknik becerilerinizi kategorize edin"
            ],
            "sector": "teknoloji",
            "fallback_mode": True
        }
    
    def get_fallback_job_match(self, resume_text: str, job_description: str) -> Dict:
        """Model çalışmadığında demo iş eşleştirme analizi döndürür"""
        return {
            "overall_match": 78,
            "skills_match": 75,
            "experience_match": 80,
            "education_match": 85,
            "requirements_match": 70,
            "matched_skills": [
                "Python programlama",
                "Veri analizi",
                "SQL veritabanı",
                "Proje yönetimi"
            ],
            "missing_skills": [
                "Machine Learning",
                "Docker containerization",
                "AWS cloud services",
                "Agile metodolojileri"
            ],
            "recommendations": [
                "Eksik becerileri öğrenmeye odaklanın",
                "İlgili sertifikalar alın",
                "Proje portföyünüzü güçlendirin",
                "Networking etkinliklerine katılın"
            ],
            "match_details": {
                "strong_points": [
                    "Teknik beceriler uyumlu",
                    "Deneyim seviyesi uygun",
                    "Eğitim geçmişi yeterli"
                ],
                "improvement_areas": [
                    "Cloud teknolojileri eksik",
                    "DevOps deneyimi sınırlı",
                    "Liderlik deneyimi az"
                ]
            },
            "fallback_mode": True
        }
    
    def extract_text_from_pdf(self, pdf_file) -> str:
        """PDF dosyasından metin çıkarır"""
        try:
            pdf_reader = PyPDF2.PdfReader(BytesIO(pdf_file.read()))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text
        except Exception as e:
            return f"PDF okuma hatası: {str(e)}"
    
    def extract_text_from_docx(self, docx_file) -> str:
        """DOCX dosyasından metin çıkarır"""
        try:
            doc = docx.Document(BytesIO(docx_file.read()))
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text
        except Exception as e:
            return f"DOCX okuma hatası: {str(e)}"
    
    def analyze_resume_ats_score(self, resume_text: str) -> Dict:
        """CV'nin ATS uyumluluğunu kapsamlı şekilde analiz eder - Gelişmiş AI ile"""
        
        # Model sağlık kontrolü - fallback mekanizması
        health_check = self.check_model_health()
        if health_check["status"] != "healthy":
            st.warning("⚠️ Model bağlantısı kurulamadı. Demo veriler gösteriliyor.")
            return self.get_fallback_ats_analysis(resume_text)
        
        # 1. Sektör Tespiti
        detected_sector = self.detect_sector(resume_text)
        
        # 2. Sektöre Özel Prompt Oluşturma
        sector_prompt = self.get_sector_specific_prompt(detected_sector, "ats")
        
        # 3. Few-Shot Examples Ekleme
        examples = self.create_few_shot_examples("ats")
        
        # 4. Ana Prompt Oluşturma
        base_prompt = f"""
        {sector_prompt}
        
        {examples}
        
        TESPİT EDİLEN SEKTÖR: {detected_sector.upper()}
        
        Aşağıdaki CV'yi analiz et ve KAPSAMLI, DETAYLI ve AKSİYON ODAKLI öneriler sun.
        Sektörel gereksinimleri göz önünde bulundurarak analiz yap.
        
        ÖNEMLI: Sadece JSON formatında yanıt ver. Her öneri spesifik ve uygulanabilir olmalı.
        
        {{
            "overall_ats_score": 0-100 arası genel ATS uyumluluk skoru,
            "section_analysis": {{
                "contact_info": {{
                    "score": 0-100,
                    "status": "Mükemmel/İyi/Orta/Zayıf",
                    "details": "detaylı açıklama ve eksik olan öğeler",
                    "missing_elements": ["telefon", "email", "LinkedIn", "konum"],
                    "specific_improvements": ["Telefon numaranızı +90 formatında ekleyin", "Profesyonel email adresi kullanın"]
                }},
                "professional_summary": {{
                    "score": 0-100,
                    "status": "Mükemmel/İyi/Orta/Zayıf/Yok",
                    "details": "mevcut durum ve iyileştirme alanları",
                    "keyword_density": "düşük/orta/yüksek",
                    "word_count": "mevcut kelime sayısı",
                    "specific_improvements": ["2-3 cümlelik özet ekleyin", "Sektörel anahtar kelimeler kullanın", "Sayısal başarılar ekleyin"]
                }},
                "work_experience": {{
                    "score": 0-100,
                    "status": "Mükemmel/İyi/Orta/Zayıf",
                    "details": "deneyim bölümünün güçlü ve zayıf yönleri",
                    "quantified_achievements": "var/yok - örnekler",
                    "action_verbs": "güçlü/zayıf - örnekler",
                    "date_format": "tutarlı/tutarsız",
                    "specific_improvements": ["Her pozisyon için 3-5 başarı ekleyin", "Sayısal sonuçlar belirtin (%20 artış gibi)", "Güçlü eylem fiilleri kullanın"]
                }},
                "education": {{
                    "score": 0-100,
                    "status": "Mükemmel/İyi/Orta/Zayıf",
                    "details": "eğitim bilgilerinin durumu",
                    "format_consistency": "tutarlı/tutarsız",
                    "specific_improvements": ["Mezuniyet tarihlerini ekleyin", "GPA ekleyin (3.0+)", "İlgili dersleri belirtin"]
                }},
                "skills": {{
                    "score": 0-100,
                    "status": "Mükemmel/İyi/Orta/Zayıf",
                    "technical_skills": ["Python", "SQL", "Excel"],
                    "soft_skills": ["Liderlik", "İletişim", "Problem Çözme"],
                    "skill_organization": "kategorize edilmiş/karışık",
                    "specific_improvements": ["Teknik ve yumuşak becerileri ayırın", "Yetkinlik seviyesi belirtin", "Sektörel becerileri öne çıkarın"]
                }}
            }},
            "format_analysis": {{
                "readability_score": 0-100,
                "font_consistency": "tutarlı/tutarsız",
                "spacing_alignment": "düzgün/düzensiz",
                "bullet_points": "uygun/yetersiz/yok",
                "length_assessment": "ideal/uzun/kısa",
                "file_format_compatibility": "uyumlu/sorunlu",
                "specific_improvements": ["Tutarlı font kullanın (Arial, Calibri)", "Başlıkları kalın yapın", "Bullet point'leri düzenleyin"]
            }},
            "keyword_analysis": {{
                "keyword_density_score": 0-100,
                "industry_keywords": ["Python", "Proje Yönetimi", "Analitik"],
                "missing_keywords": ["eksik kritik anahtar kelimeler"],
                "keyword_stuffing_risk": "düşük/orta/yüksek",
                "natural_integration": 0-100,
                "specific_improvements": ["İş tanımlarında sektörel terimler kullanın", "Beceriler bölümünü genişletin", "Başarılarda sayısal veriler ekleyin"]
            }},
            "ats_compatibility": {{
                "parsing_score": 0-100,
                "structure_score": 0-100,
                "formatting_score": 0-100,
                "compatibility_issues": ["Tablo kullanımı", "Grafik/resim var", "Karmaşık format"],
                "recommended_fixes": ["Tabloları düz metne çevirin", "Grafikleri kaldırın", "Basit format kullanın"],
                "specific_improvements": ["PDF formatında kaydedin", "Standart bölüm başlıkları kullanın", "Tek sütun düzen tercih edin"]
            }},
            "strengths": ["Güçlü teknik beceriler", "Zengin proje deneyimi", "Eğitim geçmişi", "Sertifikalar", "Liderlik deneyimi"],
            "critical_weaknesses": ["Profesyonel özet eksik", "Sayısal başarılar yok", "Anahtar kelime eksikliği", "Format sorunları", "İletişim bilgileri eksik"],
            "improvement_priority": {{
                "high_priority": ["Profesyonel özet ekleyin (2-3 cümle)", "Sayısal başarılar belirtin (%15 artış, 50 proje)", "Eksik iletişim bilgilerini tamamlayın"],
                "medium_priority": ["Anahtar kelimeleri artırın", "Beceriler bölümünü kategorize edin", "Deneyim açıklamalarını genişletin"],
                "low_priority": ["Format tutarlılığını sağlayın", "Yazım hatalarını düzeltin", "Bölüm sıralamasını optimize edin"]
            }},
            "actionable_recommendations": {{
                "immediate_actions": ["Bugün yapılabilecek değişiklikler", "Hemen eklenebilecek bilgiler", "Düzeltilebilecek formatlar"],
                "short_term_goals": ["1 hafta içinde tamamlanabilecek iyileştirmeler", "Araştırılması gereken bilgiler", "Güncellenecek bölümler"],
                "long_term_strategy": ["Kariyer hedefleri için gerekli beceriler", "Sertifika önerileri", "Deneyim geliştirme alanları"]
            }},
            "industry_alignment": {{
                "detected_industry": "Yazılım Geliştirme/Veri Analizi/Proje Yönetimi",
                "industry_standards_compliance": 0-100,
                "sector_specific_suggestions": ["Agile/Scrum deneyimi vurgulayın", "Cloud teknolojileri ekleyin", "Veri analizi projelerini öne çıkarın"],
                "trending_skills": ["Güncel sektör becerileri", "Gelişen teknolojiler", "Aranan nitelikler"]
            }},
            "success_metrics": {{
                "estimated_ats_pass_rate": "mevcut durumda ATS geçme oranı %",
                "improvement_potential": "iyileştirmeler sonrası potansiyel oran %",
                "competitive_advantage": "rakiplere göre avantajlı alanlar",
                "risk_areas": "dikkat edilmesi gereken riskli alanlar"
            }}
        }}
        """
        
        # 5. Chain-of-Thought Prompting Uygulama
        final_prompt = self.create_chain_of_thought_prompt(base_prompt, resume_text)
        
        response = self.call_local_model(final_prompt, max_tokens=4000)
        try:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_str = response[json_start:json_end]
                # JSON'u temizle
                json_str = json_str.strip()
                parsed_json = json.loads(json_str)
                return parsed_json
            else:
                # JSON bulunamadıysa, yanıtı daha detaylı incele
                lines = response.split('\n')
                json_lines = []
                in_json = False
                for line in lines:
                    if '{' in line:
                        in_json = True
                    if in_json:
                        json_lines.append(line)
                    if '}' in line and in_json:
                        break
                
                if json_lines:
                    json_str = '\n'.join(json_lines)
                    try:
                        return json.loads(json_str)
                    except:
                        pass
                
                return {"error": "JSON formatında yanıt alınamadı", "raw_response": response[:1000] + "..." if len(response) > 1000 else response}
        except json.JSONDecodeError as e:
            return {"error": f"JSON parse hatası: {str(e)}", "raw_response": response[:1000] + "..." if len(response) > 1000 else response}
    
    def match_resume_with_job(self, resume_text: str, job_description: str) -> Dict:
        """CV ile iş ilanı arasındaki uyumluluğu kapsamlı şekilde analiz eder - Gelişmiş AI ile"""
        
        # Model sağlık kontrolü - fallback mekanizması
        health_check = self.check_model_health()
        if health_check["status"] != "healthy":
            st.warning("⚠️ Model bağlantısı kurulamadı. Demo veriler gösteriliyor.")
            return self.get_fallback_job_match(resume_text, job_description)
        
        # 1. İş İlanından Sektör Tespiti
        detected_sector = self.detect_sector(job_description + " " + resume_text)
        
        # 2. Sektöre Özel Prompt Oluşturma
        sector_prompt = self.get_sector_specific_prompt(detected_sector, "job_match")
        
        # 3. Few-Shot Examples Ekleme
        examples = self.create_few_shot_examples("job_match")
        
        # 4. Ana Prompt Oluşturma
        base_prompt = f"""
        {sector_prompt}
        
        {examples}
        
        TESPİT EDİLEN SEKTÖR: {detected_sector.upper()}
        
        Aşağıdaki CV ile iş ilanı arasındaki uyumluluğu KAPSAMLI, DETAYLI ve AKSIYON ODAKLI şekilde analiz et.
        Sektörel gereksinimleri ve beklentileri göz önünde bulundurarak değerlendirme yap.
        
        ÖNEMLI: Sadece JSON formatında yanıt ver. Başka hiçbir metin ekleme. Tüm liste alanlarında maksimum 5 öğe kullan.
        
        {{
            "overall_match_score": 0-100 arası genel uyumluluk skoru,
            "detailed_analysis": {{
                "skills_analysis": {{
                    "technical_skills": {{
                        "matched": ["Python", "SQL", "Machine Learning", "Docker", "AWS"],
                        "missing": ["Kubernetes", "React", "Node.js", "MongoDB", "GraphQL"],
                        "match_percentage": 0-100,
                        "critical_missing": ["İş için kritik olan eksik beceriler"],
                        "transferable": ["Benzer teknolojilerden aktarılabilir beceriler"],
                        "proficiency_gaps": ["Beceri seviyesi açıkları (başlangıç/orta/ileri)"]
                    }},
                    "soft_skills": {{
                        "matched": ["Takım çalışması", "Liderlik", "Problem çözme", "İletişim", "Proje yönetimi"],
                        "missing": ["Müşteri odaklılık", "Analitik düşünce", "Yaratıcılık"],
                        "match_percentage": 0-100,
                        "demonstrated": ["CV'de kanıtlarla gösterilen yumuşak beceriler"],
                        "evidence_strength": ["Zayıf/Orta/Güçlü kanıt seviyeleri"]
                    }}
                }},
                "experience_analysis": {{
                    "years_match": {{
                        "required": "istenen deneyim yılı",
                        "candidate_has": "adayın deneyimi",
                        "match_status": "Uygun/Eksik/Fazla",
                        "gap_analysis": "deneyim açığı analizi"
                    }},
                    "industry_experience": {{
                        "relevant_sectors": ["ilgili sektörler"],
                        "sector_match_score": 0-100,
                        "transferable_experience": ["aktarılabilir deneyimler"]
                    }},
                    "role_similarity": {{
                        "similar_roles": ["benzer roller"],
                        "responsibility_match": 0-100,
                        "leadership_experience": "liderlik deneyimi uyumu"
                    }}
                }},
                "education_analysis": {{
                    "degree_match": {{
                        "required_degree": "istenen eğitim",
                        "candidate_degree": "adayın eğitimi",
                        "match_status": "Tam/Kısmi/Yok",
                        "alternative_qualifications": ["alternatif yeterlilikler"]
                    }},
                    "field_relevance": {{
                        "education_field": "eğitim alanı",
                        "job_field": "iş alanı",
                        "relevance_score": 0-100,
                        "additional_certifications": ["ek sertifikalar"]
                    }}
                }},
                "keyword_analysis": {{
                    "job_keywords": ["iş ilanındaki anahtar kelimeler"],
                    "resume_keywords": ["CV'deki anahtar kelimeler"],
                    "matched_keywords": ["eşleşen anahtar kelimeler"],
                    "missing_critical_keywords": ["eksik kritik anahtar kelimeler"],
                    "keyword_match_percentage": 0-100,
                    "context_relevance": "bağlamsal uygunluk değerlendirmesi"
                }}
            }},
            "compatibility_scores": {{
                "technical_compatibility": 0-100,
                "experience_compatibility": 0-100,
                "cultural_fit_indicators": 0-100,
                "growth_potential": 0-100,
                "immediate_impact_potential": 0-100
            }},
            "strengths_for_role": {{
                "top_strengths": ["bu rol için en güçlü yönler"],
                "unique_value_propositions": ["benzersiz değer önerileri"],
                "competitive_advantages": ["rekabet avantajları"]
            }},
            "gaps_and_concerns": {{
                "critical_gaps": ["kritik eksiklikler"],
                "moderate_concerns": ["orta düzey endişeler"],
                "minor_gaps": ["küçük eksiklikler"],
                "deal_breakers": ["anlaşma bozucu faktörler"]
            }},
            "improvement_roadmap": {{
                "immediate_actions": {{
                    "resume_updates": ["Proje başarılarını sayısal verilerle destekleyin", "Eksik anahtar kelimeleri ekleyin", "İş tanımlarını güçlendirin"],
                    "skill_highlighting": ["Python projelerini öne çıkarın", "Liderlik deneyimlerini vurgulayın", "Sertifikaları belirgin hale getirin"],
                    "keyword_integration": ["İş ilanındaki teknik terimleri kullanın", "Sektörel jargonu entegre edin", "Başarı metriklerini ekleyin"]
                }},
                "short_term_development": {{
                    "skills_to_acquire": ["Eksik kritik teknik beceriler", "İş için gerekli sertifikalar", "Sektörel bilgi alanları"],
                    "certifications_to_get": ["AWS Certified", "PMP", "Scrum Master", "Google Analytics", "Microsoft Azure"],
                    "experience_to_gain": ["Proje yönetimi deneyimi", "Takım liderliği", "Müşteri etkileşimi", "Bütçe yönetimi"]
                }},
                "long_term_strategy": {{
                    "career_development": ["Sektör uzmanlığı geliştirin", "Liderlik becerilerini artırın", "Ağınızı genişletin"],
                    "industry_positioning": ["Thought leadership oluşturun", "Konferanslarda konuşun", "Makaleler yazın"],
                    "network_building": ["LinkedIn'de aktif olun", "Sektör etkinliklerine katılın", "Mentörlük ilişkileri kurun"]
                }}
            }},
            "application_strategy": {{
                "cover_letter_focus": ["Spesifik proje başarılarınızı vurgulayın", "Şirket kültürüne uyumunuzu gösterin", "Somut değer önerilerinizi belirtin"],
                "interview_preparation": ["STAR metoduyla örnekler hazırlayın", "Şirket araştırması yapın", "Teknik sorulara hazırlanın"],
                "portfolio_recommendations": ["En iyi 3 projenizi seçin", "Sonuç odaklı sunumlar hazırlayın", "Teknik detayları basitleştirin"],
                "reference_strategy": ["Eski yöneticilerinizle iletişime geçin", "Proje ortaklarınızdan referans alın", "LinkedIn önerilerini güncelleyin"]
            }},
            "risk_assessment": {{
                "application_success_probability": 0-100,
                "potential_red_flags": ["Deneyim eksikliği", "Beceri açıkları", "Sektör değişikliği", "Aşırı nitelik", "Kariyer boşlukları"],
                "mitigation_strategies": ["Transferable becerilerinizi vurgulayın", "Öğrenme isteğinizi gösterin", "Esnekliğinizi belirtin"],
                "success_factors": ["Güçlü yönlerinizi öne çıkarın", "Şirket ihtiyaçlarına odaklanın", "Kültürel uyumu vurgulayın"]
            }}
        }}
        """
        
        # 5. Chain-of-Thought Prompting Uygulama
        context = f"CV Metni:\n{resume_text}\n\nİş İlanı:\n{job_description}"
        final_prompt = self.create_chain_of_thought_prompt(base_prompt, context)
        
        response = self.call_local_model(final_prompt, max_tokens=4500)
        try:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_str = response[json_start:json_end]
                # JSON'u temizle
                json_str = json_str.strip()
                parsed_json = json.loads(json_str)
                return parsed_json
            else:
                # JSON bulunamadıysa, yanıtı daha detaylı incele
                lines = response.split('\n')
                json_lines = []
                in_json = False
                for line in lines:
                    if '{' in line:
                        in_json = True
                    if in_json:
                        json_lines.append(line)
                    if '}' in line and in_json:
                        break
                
                if json_lines:
                    json_str = '\n'.join(json_lines)
                    try:
                        return json.loads(json_str)
                    except:
                        pass
                
                return {"error": "JSON formatında yanıt alınamadı", "raw_response": response[:1000] + "..." if len(response) > 1000 else response}
        except json.JSONDecodeError as e:
            return {"error": f"JSON parse hatası: {str(e)}", "raw_response": response[:1000] + "..." if len(response) > 1000 else response}

def display_score_gauge(score, title, color_scheme="blue"):
    """Skor göstergesi oluşturur"""
    if score >= 80:
        color = "🟢"
        status = "Mükemmel"
    elif score >= 60:
        color = "🟡"
        status = "İyi"
    elif score >= 40:
        color = "🟠"
        status = "Orta"
    else:
        color = "🔴"
        status = "Zayıf"
    
    return f"{color} **{title}**: {score}/100 ({status})"

def display_ats_analysis(ats_result):
    """ATS analiz sonuçlarını görüntüler"""
    if "error" in ats_result:
        st.error("❌ Analiz hatası!")
        st.error(ats_result.get('raw_response', 'Bilinmeyen hata'))
        return
    
    # Fallback mode kontrolü
    if ats_result.get('fallback_mode', False):
        st.info("🔄 Demo veriler gösteriliyor - Model bağlantısı kurulamadı")
    
    # Ana skor
    overall_score = ats_result.get('overall_score', ats_result.get('overall_ats_score', 0))
    st.markdown(f"## 🎯 Genel ATS Skoru: {overall_score}/100")
    
    # Skor göstergesi
    progress_color = "green" if overall_score >= 70 else "orange" if overall_score >= 50 else "red"
    st.progress(overall_score / 100)
    
    # Fallback mode için basit görüntüleme
    if ats_result.get('fallback_mode', False):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("📧 İletişim", f"{ats_result.get('contact_score', 90)}/100")
            st.metric("🎯 Anahtar Kelime", f"{ats_result.get('keyword_score', 70)}/100")
        
        with col2:
            st.metric("📄 Format", f"{ats_result.get('format_score', 85)}/100")
            st.metric("💼 Deneyim", f"{ats_result.get('experience_score', 80)}/100")
        
        with col3:
            st.metric("🎓 Eğitim", f"{ats_result.get('education_score', 75)}/100")
            st.metric("💡 Beceriler", f"{ats_result.get('skills_score', 85)}/100")
        
        # Güçlü yönler
        if 'strengths' in ats_result:
            st.markdown("### ✅ Güçlü Yönler")
            for strength in ats_result['strengths']:
                st.success(strength)
        
        # İyileştirme önerileri
        if 'improvements' in ats_result:
            st.markdown("### 🔧 İyileştirme Önerileri")
            for improvement in ats_result['improvements']:
                st.warning(improvement)
        
        # Genel öneriler
        if 'recommendations' in ats_result:
            st.markdown("### 💡 Genel Öneriler")
            for recommendation in ats_result['recommendations']:
                st.info(recommendation)
        
        return
    
    # Bölüm analizleri
    if 'section_analysis' in ats_result:
        st.markdown("### 📊 Bölüm Bazında Analiz")
        
        sections = ats_result['section_analysis']
        col1, col2 = st.columns(2)
        
        with col1:
            # İletişim Bilgileri
            if 'contact_info' in sections:
                contact = sections['contact_info']
                st.markdown(f"#### 📞 İletişim Bilgileri")
                st.markdown(display_score_gauge(contact.get('score', 0), "Skor"))
                st.markdown(f"**Durum**: {contact.get('status', 'Bilinmiyor')}")
                st.markdown(f"**Detay**: {contact.get('details', 'Bilgi yok')}")
                if contact.get('missing_elements'):
                    st.warning("Eksik öğeler: " + ", ".join(contact['missing_elements']))
            
            # Çalışma Deneyimi
            if 'work_experience' in sections:
                work = sections['work_experience']
                st.markdown(f"#### 💼 Çalışma Deneyimi")
                st.markdown(display_score_gauge(work.get('score', 0), "Skor"))
                st.markdown(f"**Durum**: {work.get('status', 'Bilinmiyor')}")
                st.markdown(f"**Detay**: {work.get('details', 'Bilgi yok')}")
                if work.get('quantified_achievements'):
                    st.info(f"📈 Sayısal Başarılar: {work['quantified_achievements']}")
                if work.get('action_verbs'):
                    st.info(f"💪 Eylem Fiilleri: {work['action_verbs']}")
        
        with col2:
            # Profesyonel Özet
            if 'professional_summary' in sections:
                summary = sections['professional_summary']
                st.markdown(f"#### 📝 Profesyonel Özet")
                st.markdown(display_score_gauge(summary.get('score', 0), "Skor"))
                st.markdown(f"**Durum**: {summary.get('status', 'Bilinmiyor')}")
                st.markdown(f"**Detay**: {summary.get('details', 'Bilgi yok')}")
                if summary.get('keyword_density'):
                    st.info(f"🔑 Anahtar Kelime Yoğunluğu: {summary['keyword_density']}")
            
            # Beceriler
            if 'skills' in sections:
                skills = sections['skills']
                st.markdown(f"#### 🛠️ Beceriler")
                st.markdown(display_score_gauge(skills.get('score', 0), "Skor"))
                st.markdown(f"**Durum**: {skills.get('status', 'Bilinmiyor')}")
                if skills.get('technical_skills'):
                    st.success("**Teknik Beceriler**: " + ", ".join(skills['technical_skills'][:3]))
                if skills.get('soft_skills'):
                    st.success("**Yumuşak Beceriler**: " + ", ".join(skills['soft_skills'][:3]))
    
    # Format Analizi
    if 'format_analysis' in ats_result:
        st.markdown("### 🎨 Format Analizi")
        format_data = ats_result['format_analysis']
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Okunabilirlik", f"{format_data.get('readability_score', 0)}/100")
        with col2:
            st.metric("Font Tutarlılığı", format_data.get('font_consistency', 'Bilinmiyor'))
        with col3:
            st.metric("Dosya Uyumluluğu", format_data.get('file_format_compatibility', 'Bilinmiyor'))
    
    # Anahtar Kelime Analizi
    if 'keyword_analysis' in ats_result:
        st.markdown("### 🔑 Anahtar Kelime Analizi")
        keyword_data = ats_result['keyword_analysis']
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Anahtar Kelime Skoru", f"{keyword_data.get('keyword_density_score', 0)}/100")
            if keyword_data.get('industry_keywords'):
                st.success("**Sektör Anahtar Kelimeleri**:")
                for kw in keyword_data['industry_keywords'][:5]:
                    st.write(f"• {kw}")
        
        with col2:
            st.metric("Doğal Entegrasyon", f"{keyword_data.get('natural_integration', 0)}/100")
            if keyword_data.get('missing_keywords'):
                st.warning("**Eksik Anahtar Kelimeler**:")
                for kw in keyword_data['missing_keywords'][:5]:
                    st.write(f"• {kw}")
    
    # İyileştirme Önerileri
    if 'improvement_priority' in ats_result:
        st.markdown("### 🚀 İyileştirme Önerileri")
        priorities = ats_result['improvement_priority']
        
        tab1, tab2, tab3 = st.tabs(["🔴 Yüksek Öncelik", "🟡 Orta Öncelik", "🟢 Düşük Öncelik"])
        
        with tab1:
            if priorities.get('high_priority'):
                for item in priorities['high_priority']:
                    st.error(f"🔴 {item}")
        
        with tab2:
            if priorities.get('medium_priority'):
                for item in priorities['medium_priority']:
                    st.warning(f"🟡 {item}")
        
        with tab3:
            if priorities.get('low_priority'):
                for item in priorities['low_priority']:
                    st.info(f"🟢 {item}")

def display_job_match_analysis(match_result):
    """İş eşleştirme analiz sonuçlarını görüntüler"""
    if "error" in match_result:
        st.error("❌ Eşleştirme analizi hatası!")
        st.error(match_result.get('raw_response', 'Bilinmeyen hata'))
        return
    
    # Fallback mode kontrolü
    if match_result.get('fallback_mode', False):
        st.info("🔄 Demo veriler gösteriliyor - Model bağlantısı kurulamadı")
    
    # Ana skor
    overall_score = match_result.get('overall_match', match_result.get('overall_match_score', 0))
    st.markdown(f"## 🎯 Genel Uyumluluk Skoru: {overall_score}/100")
    st.progress(overall_score / 100)
    
    # Fallback mode için basit görüntüleme
    if match_result.get('fallback_mode', False):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("💡 Beceri Uyumu", f"{match_result.get('skills_match', 75)}/100")
            st.metric("💼 Deneyim Uyumu", f"{match_result.get('experience_match', 80)}/100")
        
        with col2:
            st.metric("🎓 Eğitim Uyumu", f"{match_result.get('education_match', 85)}/100")
            st.metric("📋 Gereksinim Uyumu", f"{match_result.get('requirements_match', 70)}/100")
        
        with col3:
            st.metric("🎯 Toplam Uyum", f"{overall_score}/100")
        
        # Eşleşen beceriler
        if 'matched_skills' in match_result:
            st.markdown("### ✅ Eşleşen Beceriler")
            for skill in match_result['matched_skills']:
                st.success(f"✓ {skill}")
        
        # Eksik beceriler
        if 'missing_skills' in match_result:
            st.markdown("### ❌ Eksik Beceriler")
            for skill in match_result['missing_skills']:
                st.warning(f"⚠️ {skill}")
        
        # Öneriler
        if 'recommendations' in match_result:
            st.markdown("### 💡 Öneriler")
            for recommendation in match_result['recommendations']:
                st.info(recommendation)
        
        return
    
    # Uyumluluk skorları
    if 'compatibility_scores' in match_result:
        st.markdown("### 📊 Uyumluluk Skorları")
        scores = match_result['compatibility_scores']
        
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Teknik", f"{scores.get('technical_compatibility', 0)}/100")
        with col2:
            st.metric("Deneyim", f"{scores.get('experience_compatibility', 0)}/100")
        with col3:
            st.metric("Kültürel Uyum", f"{scores.get('cultural_fit_indicators', 0)}/100")
        with col4:
            st.metric("Büyüme Potansiyeli", f"{scores.get('growth_potential', 0)}/100")
        with col5:
            st.metric("Hızlı Etki", f"{scores.get('immediate_impact_potential', 0)}/100")
    
    # Detaylı analiz
    if 'detailed_analysis' in match_result:
        analysis = match_result['detailed_analysis']
        
        # Beceri analizi
        if 'skills_analysis' in analysis:
            st.markdown("### 🛠️ Beceri Analizi")
            skills = analysis['skills_analysis']
            
            col1, col2 = st.columns(2)
            with col1:
                if 'technical_skills' in skills:
                    tech = skills['technical_skills']
                    st.markdown("#### 💻 Teknik Beceriler")
                    st.metric("Eşleşme Oranı", f"{tech.get('match_percentage', 0)}%")
                    
                    if tech.get('matched'):
                        st.success("**Eşleşen Beceriler**:")
                        for skill in tech['matched'][:5]:
                            st.write(f"✅ {skill}")
                    
                    if tech.get('critical_missing'):
                        st.error("**Kritik Eksik Beceriler**:")
                        for skill in tech['critical_missing'][:3]:
                            st.write(f"❌ {skill}")
            
            with col2:
                if 'soft_skills' in skills:
                    soft = skills['soft_skills']
                    st.markdown("#### 🤝 Yumuşak Beceriler")
                    st.metric("Eşleşme Oranı", f"{soft.get('match_percentage', 0)}%")
                    
                    if soft.get('matched'):
                        st.success("**Eşleşen Beceriler**:")
                        for skill in soft['matched'][:5]:
                            st.write(f"✅ {skill}")
    
    # Güçlü yönler ve eksiklikler
    col1, col2 = st.columns(2)
    with col1:
        if 'strengths_for_role' in match_result:
            st.markdown("### 💪 Bu Rol İçin Güçlü Yönler")
            strengths = match_result['strengths_for_role']
            if strengths.get('top_strengths'):
                for strength in strengths['top_strengths']:
                    st.success(f"✅ {strength}")
    
    with col2:
        if 'gaps_and_concerns' in match_result:
            st.markdown("### ⚠️ Eksiklikler ve Endişeler")
            gaps = match_result['gaps_and_concerns']
            if gaps.get('critical_gaps'):
                for gap in gaps['critical_gaps']:
                    st.error(f"❌ {gap}")
    
    # İyileştirme yol haritası
    if 'improvement_roadmap' in match_result:
        st.markdown("### 🗺️ İyileştirme Yol Haritası")
        roadmap = match_result['improvement_roadmap']
        
        tab1, tab2, tab3 = st.tabs(["🚀 Hemen Yapılacaklar", "📅 Kısa Vadeli", "🎯 Uzun Vadeli"])
        
        with tab1:
            if 'immediate_actions' in roadmap:
                immediate = roadmap['immediate_actions']
                if immediate.get('resume_updates'):
                    st.markdown("**CV Güncellemeleri:**")
                    for update in immediate['resume_updates']:
                        st.info(f"📝 {update}")
        
        with tab2:
            if 'short_term_development' in roadmap:
                short_term = roadmap['short_term_development']
                if short_term.get('skills_to_acquire'):
                    st.markdown("**Kazanılacak Beceriler:**")
                    for skill in short_term['skills_to_acquire']:
                        st.warning(f"🎓 {skill}")
        
        with tab3:
            if 'long_term_strategy' in roadmap:
                long_term = roadmap['long_term_strategy']
                if long_term.get('career_development'):
                    st.markdown("**Kariyer Geliştirme:**")
                    for dev in long_term['career_development']:
                        st.info(f"🚀 {dev}")

def main():
    # Veritabanı yöneticisini başlat
    db_manager = DatabaseManager()
    
    # Tabloları oluştur (ilk çalıştırmada)
    if 'tables_created' not in st.session_state:
        with st.spinner("🗄️ Veritabanı hazırlanıyor..."):
            if db_manager.create_tables():
                st.session_state.tables_created = True
                st.success("✅ Veritabanı hazır!")
            else:
                st.error("❌ Veritabanı bağlantı sorunu!")
    
    # CSS stilleri
    st.markdown("""
    <style>
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .feature-box {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #667eea;
        margin: 1rem 0;
    }
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Ana başlık
    st.markdown("""
    <div class="main-header">
        <h1>🎯 ATS Resume Analyzer Pro</h1>
        <p>Yapay zeka destekli profesyonel CV analizi ve iş ilanı uyumluluk değerlendirmesi</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Özellikler
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""
        <div class="feature-box">
            <h4>📊 Detaylı ATS Analizi</h4>
            <p>CV'nizin ATS sistemlerindeki performansını kapsamlı şekilde değerlendirin</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="feature-box">
            <h4>🎯 İş İlanı Uyumluluğu</h4>
            <p>CV'nizin belirli iş ilanlarıyla ne kadar uyumlu olduğunu öğrenin</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="feature-box">
            <h4>💡 Aksiyon Odaklı Öneriler</h4>
            <p>Somut iyileştirme önerileri ve kariyer geliştirme stratejileri alın</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.markdown("## 📋 Kontrol Paneli")
        
        # Model durumu
        st.markdown("### 🤖 Model Durumu")
        analyzer = ATSAnalyzer()
        
        # Real-time model health check
        health_status = analyzer.check_model_health()
        
        # Status indicator
        if health_status["status"] == "healthy":
            st.success(f"✅ {health_status['message']}")
            model_status_color = "🟢"
        elif health_status["status"] == "timeout":
            st.warning(f"⏱️ {health_status['message']}")
            model_status_color = "🟡"
        elif health_status["status"] == "connection_error":
            st.error(f"🔌 {health_status['message']}")
            model_status_color = "🔴"
        else:
            st.error(f"❌ {health_status['message']}")
            model_status_color = "🔴"
        
        # Model bilgileri
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Durum", model_status_color, help="Model bağlantı durumu")
        with col2:
            st.metric("Port", "1234", help="LM Studio port")
        
        # Progress indicator (eğer model çağrısı yapılıyorsa)
        if 'model_call_progress' in st.session_state:
            st.info(st.session_state.model_call_progress)
        
        # Manuel test butonu
        if st.button("🔄 Durumu Yenile", use_container_width=True):
            st.rerun()
        
        # Detaylı test butonu
        with st.expander("🔧 Gelişmiş Test"):
            if st.button("📡 Detaylı Bağlantı Testi"):
                with st.spinner("Detaylı test yapılıyor..."):
                    test_response = analyzer.call_local_model("Bu bir test mesajıdır.", max_tokens=20)
                    if any(error in test_response for error in ["❌", "⏱️", "🔌", "🌐", "📄"]):
                        st.error(f"Test başarısız: {test_response}")
                    else:
                        st.success("✅ Detaylı test başarılı!")
                        st.code(test_response[:100] + "..." if len(test_response) > 100 else test_response)
        
        st.markdown("### 🎛️ Analiz Seçenekleri")
        analysis_mode = st.radio(
            "Analiz türünü seçin:",
            ["🎯 Sadece ATS Analizi", "🔄 Sadece İş Eşleştirme", "🚀 Kapsamlı Analiz"],
            help="Analiz türüne göre farklı özellikler aktif olur"
        )
        
        # İstatistikler
        st.markdown("### 📊 Veritabanı İstatistikleri")
        stats = db_manager.get_analysis_stats()
        
        if stats:
            col1, col2 = st.columns(2)
            with col1:
                st.metric("📄 Toplam CV", stats.get('total_resumes', 0))
                st.metric("🎯 ATS Analizi", stats.get('total_analyses', 0))
            with col2:
                st.metric("🔄 İş Eşleştirme", stats.get('total_job_matches', 0))
                avg_score = stats.get('avg_ats_score', 0)
                if avg_score:
                    st.metric("📊 Ort. ATS Skoru", f"{avg_score:.1f}")
                else:
                    st.metric("📊 Ort. ATS Skoru", "N/A")
        
        # CV Geçmişi
        st.markdown("### 📋 Son CV'ler")
        recent_resumes = db_manager.get_resume_history(limit=5)
        
        if recent_resumes:
            for resume in recent_resumes:
                with st.expander(f"📄 {resume['title'][:30]}...", expanded=False):
                    st.write(f"**Dosya:** {resume['file_name']}")
                    st.write(f"**Sektör:** {resume['sector']}")
                    st.write(f"**Tarih:** {resume['created_at'].strftime('%Y-%m-%d %H:%M')}")
                    st.write(f"**Analiz Sayısı:** {resume['analysis_count']}")
                    st.write(f"**İş Eşleştirme:** {resume['job_match_count']}")
        else:
            st.info("Henüz CV analizi yapılmamış")
        
        st.markdown("---")
        st.info("💡 **İpucu**: En iyi sonuçlar için CV'nizin PDF formatında olmasını sağlayın")
    
    # Ana içerik alanı
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # CV seçim arayüzü
        st.markdown("## 📄 CV Seçimi")
        
        # Tab'lar ile yeni yükleme ve mevcut CV seçimi
        tab1, tab2 = st.tabs(["📤 Yeni CV Yükle", "📋 Mevcut CV'leri Seç"])
        
        with tab1:
            uploaded_file = st.file_uploader(
                "CV dosyanızı sürükleyip bırakın veya seçin",
                type=['pdf', 'docx'],
                help="Desteklenen formatlar: PDF, DOCX (Maksimum 10MB)"
            )
        
        with tab2:
            # Mevcut CV'leri getir
            existing_resumes = db_manager.get_all_resumes_for_selection()
            
            if existing_resumes:
                # CV seçim dropdown'u
                resume_options = {}
                for resume in existing_resumes:
                    display_name = f"📄 {resume['title'][:40]}... ({resume['created_at'].strftime('%Y-%m-%d')})"
                    resume_options[display_name] = resume
                
                selected_resume_display = st.selectbox(
                    "Analiz etmek istediğiniz CV'yi seçin:",
                    options=["Seçim yapın..."] + list(resume_options.keys()),
                    help="Daha önce yüklediğiniz CV'lerden birini seçebilirsiniz"
                )
                
                if selected_resume_display != "Seçim yapın...":
                    selected_resume = resume_options[selected_resume_display]
                    
                    # Seçilen CV bilgilerini göster
                    col_info1, col_info2 = st.columns(2)
                    with col_info1:
                        st.info(f"📁 **Dosya:** {selected_resume['file_name']}")
                        st.info(f"🏢 **Sektör:** {selected_resume['sector']}")
                    with col_info2:
                        st.info(f"📅 **Tarih:** {selected_resume['created_at'].strftime('%Y-%m-%d %H:%M')}")
                        st.info(f"📊 **Analiz:** {selected_resume['analysis_count']} | **Eşleştirme:** {selected_resume['job_match_count']}")
                    
                    # CV'yi session state'e yükle
                    if st.button("🎯 Bu CV'yi Analiz Et", type="primary"):
                        resume_data = db_manager.get_resume_by_id(selected_resume['id'])
                        if resume_data:
                            st.session_state.selected_resume_text = resume_data['extracted_text']
                            st.session_state.selected_resume_sector = resume_data['sector']
                            st.session_state.current_resume_id = resume_data['id']
                            st.session_state.selected_resume_title = resume_data['title']
                            st.success("✅ CV seçildi! Aşağıdan analiz türünü seçebilirsiniz.")
                            st.rerun()
            else:
                st.info("📝 Henüz yüklenmiş CV bulunmuyor. Yukarıdaki sekmeden yeni bir CV yükleyebilirsiniz.")
        
        # Seçilen CV varsa göster
        if 'selected_resume_text' in st.session_state:
            st.success(f"✅ **Seçili CV:** {st.session_state.get('selected_resume_title', 'Bilinmeyen')}")
            resume_text = st.session_state.selected_resume_text
            detected_sector = st.session_state.selected_resume_sector
            
            # CV önizleme
            with st.expander("📖 CV İçeriğini Görüntüle", expanded=False):
                st.text_area("CV Metni:", resume_text, height=200, disabled=True)
        
        # Yeni yüklenen dosya varsa işle
        elif 'uploaded_file' in locals() and uploaded_file is not None:
        
            resume_text = ""
            with st.spinner("📖 CV okunuyor ve işleniyor..."):
                if uploaded_file.type == "application/pdf":
                    resume_text = analyzer.extract_text_from_pdf(uploaded_file)
                elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                    resume_text = analyzer.extract_text_from_docx(uploaded_file)
                
                if resume_text and not resume_text.startswith("Hata"):
                    st.success(f"✅ CV başarıyla yüklendi! ({len(resume_text)} karakter)")
                    
                    # Sektör Tespiti
                    detected_sector = analyzer.detect_sector(resume_text)
                    sector_emoji = {
                        "teknoloji": "💻",
                        "finans": "💰", 
                        "sağlık": "🏥",
                        "eğitim": "🎓",
                        "pazarlama": "📈",
                        "satış": "🤝",
                        "genel": "🏢"
                    }
                    
                    st.info(f"🎯 **Tespit Edilen Sektör:** {sector_emoji.get(detected_sector, '🏢')} {detected_sector.title()}")
                    
                    # CV'yi veritabanına kaydet (duplicate kontrolü ile)
                    resume_title = f"CV - {uploaded_file.name} - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    save_result = db_manager.save_resume(
                        title=resume_title,
                        file_name=uploaded_file.name,
                        extracted_text=resume_text,
                        sector=detected_sector
                    )
                    
                    if save_result['success']:
                        if save_result['is_duplicate']:
                            st.warning("⚠️ Bu CV daha önce yüklenmiş! Mevcut CV kullanılacak.")
                        else:
                            st.success("💾 CV veritabanına kaydedildi!")
                        
                        st.session_state.current_resume_id = save_result['resume_id']
                        st.session_state.selected_resume_text = resume_text
                        st.session_state.selected_resume_sector = detected_sector
                        st.session_state.selected_resume_title = resume_title
                    else:
                        st.error("❌ CV kaydedilemedi!")
                    
                    # CV önizleme
                    with st.expander("📖 CV İçeriğini Görüntüle", expanded=False):
                        st.text_area("CV Metni:", resume_text, height=200, disabled=True)
                else:
                    st.error("❌ CV okuma hatası!")
                    st.error(resume_text)
    
    with col2:
        # Yardım ve bilgi paneli
        st.markdown("## ℹ️ Yardım")
        
        with st.expander("🎯 ATS Nedir?", expanded=True):
            st.markdown("""
            **ATS (Applicant Tracking System)** şirketlerin CV'leri otomatik olarak 
            tarayıp değerlendirdiği sistemlerdir. Bu sistem:
            
            - 📊 CV'nizi otomatik skorlar
            - 🔍 Anahtar kelimeleri arar
            - 📋 Bölüm organizasyonunu kontrol eder
            - ✅ Format uyumluluğunu değerlendirir
            """)
        
        with st.expander("💡 İpuçları"):
            st.markdown("""
            **En İyi Sonuçlar İçin:**
            
            - 📄 PDF formatını tercih edin
            - 🔑 İş ilanındaki anahtar kelimeleri kullanın
            - 📊 Sayısal başarılarınızı belirtin
            - 🎯 Her pozisyon için CV'nizi özelleştirin
            - 📝 Basit ve temiz format kullanın
            """)
    
    # CV seçilmiş mi kontrol et
    resume_text = ""
    detected_sector = ""
    
    if 'selected_resume_text' in st.session_state:
        resume_text = st.session_state.selected_resume_text
        detected_sector = st.session_state.selected_resume_sector
    
    # Analiz bölümü
    if resume_text and not resume_text.startswith("Hata"):
        st.markdown("---")
        
        # İş ilanı girişi (eğer gerekiyorsa)
        job_description = ""
        if analysis_mode in ["🔄 Sadece İş Eşleştirme", "🚀 Kapsamlı Analiz"]:
            st.markdown("## 📋 İş İlanı")
            job_description = st.text_area(
                "İş ilanının tam metnini yapıştırın:",
                height=150,
                placeholder="İş tanımı, gereksinimler, aranan nitelikler vb. tüm metni buraya yapıştırın...",
                help="Ne kadar detaylı olursa analiz o kadar doğru olur"
            )
        
        # Analiz başlatma
        if st.button("🚀 Analizi Başlat", type="primary", use_container_width=True):
            
            if analysis_mode == "🎯 Sadece ATS Analizi":
                with st.spinner("🔍 ATS uyumluluğu analiz ediliyor..."):
                    ats_result = analyzer.analyze_resume_ats_score(resume_text)
                    
                    # Sonucu veritabanına kaydet
                    if 'current_resume_id' in st.session_state and 'error' not in ats_result:
                        db_manager.save_ats_analysis(st.session_state.current_resume_id, ats_result)
                    
                    st.markdown("## 📊 ATS Analiz Sonuçları")
                    display_ats_analysis(ats_result)
            
            elif analysis_mode == "🔄 Sadece İş Eşleştirme":
                if not job_description.strip():
                    st.warning("⚠️ İş ilanı metni gerekli!")
                else:
                    with st.spinner("🔄 İş ilanı ile eşleştirme yapılıyor..."):
                        match_result = analyzer.match_resume_with_job(resume_text, job_description)
                        
                        # Sonucu veritabanına kaydet
                        if 'current_resume_id' in st.session_state and 'error' not in match_result:
                            job_title = job_description.split('\n')[0][:100]  # İlk satırdan iş başlığını al
                            db_manager.save_job_match(
                                st.session_state.current_resume_id, 
                                job_title, 
                                job_description, 
                                match_result
                            )
                        
                        st.markdown("## 🎯 İş Eşleştirme Sonuçları")
                        display_job_match_analysis(match_result)
            
            elif analysis_mode == "🚀 Kapsamlı Analiz":
                with st.spinner("🚀 Kapsamlı analiz yapılıyor... Bu biraz zaman alabilir."):
                    # Her iki analizi de yap
                    ats_result = analyzer.analyze_resume_ats_score(resume_text)
                    
                    # ATS sonucunu kaydet
                    if 'current_resume_id' in st.session_state and 'error' not in ats_result:
                        db_manager.save_ats_analysis(st.session_state.current_resume_id, ats_result)
                    
                    match_result = None
                    if job_description.strip():
                        match_result = analyzer.match_resume_with_job(resume_text, job_description)
                        
                        # İş eşleştirme sonucunu kaydet
                        if 'current_resume_id' in st.session_state and match_result and 'error' not in match_result:
                            job_title = job_description.split('\n')[0][:100]
                            db_manager.save_job_match(
                                st.session_state.current_resume_id, 
                                job_title, 
                                job_description, 
                                match_result
                            )
                    
                    # Sonuçları göster
                    st.markdown("## 📈 Kapsamlı Analiz Sonuçları")
                    
                    # Ana skorlar
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        ats_score = ats_result.get('overall_ats_score', 0) if 'error' not in ats_result else 0
                        st.metric("🎯 ATS Skoru", f"{ats_score}/100")
                    
                    with col2:
                        if match_result and 'error' not in match_result:
                            match_score = match_result.get('overall_match_score', 0)
                            st.metric("🔄 Eşleşme Skoru", f"{match_score}/100")
                        else:
                            st.metric("🔄 Eşleşme Skoru", "N/A")
                    
                    with col3:
                        if match_result and 'error' not in match_result:
                            avg_score = (ats_score + match_result.get('overall_match_score', 0)) / 2
                            st.metric("📊 Ortalama Skor", f"{avg_score:.0f}/100")
                        else:
                            st.metric("📊 Genel Skor", f"{ats_score}/100")
                    
                    # Detaylı sonuçlar
                    tab1, tab2 = st.tabs(["🎯 ATS Analizi", "🔄 İş Eşleştirme"])
                    
                    with tab1:
                        display_ats_analysis(ats_result)
                    
                    with tab2:
                        if match_result:
                            display_job_match_analysis(match_result)
                        elif job_description.strip():
                            st.error("❌ İş eşleştirme analizi başarısız!")
                        else:
                            st.info("💡 İş ilanı ekleyerek eşleştirme analizi de yapabilirsiniz.")
    
    else:
        # Başlangıç ekranı
        st.markdown("---")
        st.markdown("""
        ## 🚀 Başlamak İçin
        
        1. **📄 CV'nizi yükleyin** (PDF veya DOCX formatında)
        2. **🎛️ Analiz türünü seçin** (soldaki panelden)
        3. **📋 İş ilanını ekleyin** (eşleştirme analizi için)
        4. **🚀 Analizi başlatın** ve sonuçları inceleyin!
        
        ### 🎯 Neler Yapabilirsiniz?
        
        - ✅ **ATS Uyumluluk Skoru** - CV'nizin ATS sistemlerinde ne kadar başarılı olacağını öğrenin
        - 🔄 **İş Eşleştirme Analizi** - Belirli bir iş ilanı için uyumluluğunuzu değerlendirin  
        - 📊 **Detaylı Raporlar** - Bölüm bazında analiz ve iyileştirme önerileri
        - 🚀 **Aksiyon Planı** - Öncelikli iyileştirme adımları
        - 💡 **Profesyonel Öneriler** - Uzman tavsiyeleri ve ipuçları
        """)
        
        # Örnek görseller veya demo
        col1, col2, col3 = st.columns(3)
        with col1:
            st.info("🎯 **ATS Skoru**\nCV'nizin otomatik tarama sistemlerindeki performansı")
        with col2:
            st.info("🔄 **Eşleşme Analizi**\nİş ilanı ile uyumluluk değerlendirmesi")
        with col3:
            st.info("📊 **Detaylı Rapor**\nKapsamlı analiz ve iyileştirme önerileri")

if __name__ == "__main__":
    main()