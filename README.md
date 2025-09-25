# 🎯 ATS Resume Analyzer

Bu uygulama, CV'lerinizi ATS (Applicant Tracking System) uyumluluğu açısından analiz eder ve iş ilanlarıyla eşleştirme yapar. Lokal olarak çalışan Qwen3-4B-Instruct modelini kullanarak gerçek zamanlı analiz ve öneriler sunar.

## ✨ Özellikler

- 📄 **Dosya Desteği**: PDF ve DOCX formatında CV yükleme
- 🎯 **ATS Uyumluluk Analizi**: CV'nin ATS sistemlerine uygunluğunu değerlendirme
- 🔍 **İş İlanı Eşleştirme**: CV ile iş ilanı arasındaki uyumu analiz etme
- 💡 **Akıllı Öneriler**: AI destekli iyileştirme önerileri
- 🚀 **Öncelikli Aksiyonlar**: En önemli geliştirme alanlarını belirleme
- 📊 **Detaylı Skorlama**: ATS skoru ve eşleşme oranı hesaplama
- 🔑 **Anahtar Kelime Analizi**: Eksik ve eşleşen anahtar kelimeleri tespit etme

## 🛠️ Kurulum

### Gereksinimler

- Python 3.8+
- Lokal olarak çalışan Qwen3-4B-Instruct modeli (http://127.0.0.1:1234)

### Adımlar

1. **Projeyi klonlayın veya indirin**

2. **Gerekli paketleri yükleyin:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Lokal AI modelinizin çalıştığından emin olun**
   - Model URL: `http://127.0.0.1:1234`
   - Model: `qwen/qwen3-4b-2507`

4. **Uygulamayı başlatın:**
   ```bash
   streamlit run app.py
   ```

5. **Tarayıcınızda açın:**
   - Varsayılan adres: `http://localhost:8501`

## 🚀 Kullanım

### 1. Model Bağlantısını Test Edin
- Sol menüden "Model Bağlantısını Test Et" butonuna tıklayın
- Yeşil onay işareti görürseniz model hazır

### 2. CV Yükleyin
- "CV Yükleme" bölümünden PDF veya DOCX dosyanızı seçin
- Dosya başarıyla yüklendiğinde yeşil onay mesajı görünür

### 3. Analiz Türünü Seçin

#### 🎯 ATS Uyumluluk Analizi
- CV'nizin ATS sistemlerine ne kadar uygun olduğunu öğrenin
- Güçlü ve zayıf yönlerinizi görün
- Eksik bölümleri tespit edin
- İyileştirme önerileri alın

#### 🔍 İş İlanı Eşleştirme
- İş ilanı metnini yapıştırın
- CV'niz ile iş ilanı arasındaki eşleşme oranını görün
- Eksik becerileri ve anahtar kelimeleri öğrenin
- Öncelikli geliştirme alanlarını belirleyin

#### 📊 Kapsamlı Analiz
- Hem ATS analizi hem de iş ilanı eşleştirmesi
- Tüm sonuçları tek ekranda görüntüleyin
- En kapsamlı değerlendirme için önerilen seçenek

## 🔧 Teknik Detaylar

### Model Entegrasyonu
- **Model**: Qwen3-4B-Instruct
- **API**: OpenAI uyumlu REST API
- **Endpoint**: `/v1/chat/completions`
- **Timeout**: 30 saniye

### Desteklenen Dosya Formatları
- **PDF**: PyPDF2 kütüphanesi ile metin çıkarma
- **DOCX**: python-docx kütüphanesi ile metin çıkarma

### Analiz Kriterleri

#### ATS Uyumluluk
- Anahtar kelime kullanımı
- Bölüm organizasyonu
- Ölçülebilir başarılar
- Teknik beceriler
- Format uyumluluğu

#### İş İlanı Eşleştirme
- Beceri eşleşmesi
- Anahtar kelime analizi
- Deneyim uyumu
- Eğitim uyumu
- Genel uyumluluk skoru

## 🎨 Arayüz Özellikleri

- **Modern Tasarım**: Streamlit tabanlı kullanıcı dostu arayüz
- **Responsive Layout**: Geniş ekran desteği
- **Renkli Göstergeler**: Başarı, uyarı ve hata mesajları
- **İnteraktif Bileşenler**: Genişletilebilir bölümler ve sekmeler
- **Gerçek Zamanlı Feedback**: Yükleme animasyonları ve durum mesajları

## 🔧 Konfigürasyon

Model URL'sini değiştirmek için `app.py` dosyasındaki `ATSAnalyzer` sınıfını düzenleyin:

```python
analyzer = ATSAnalyzer(model_url="http://your-model-url:port")
```

## 🐛 Sorun Giderme

### Model Bağlantı Sorunları
- Model servisinin çalıştığından emin olun
- URL ve port numarasını kontrol edin
- Firewall ayarlarını kontrol edin

### Dosya Okuma Sorunları
- Dosya formatının desteklendiğinden emin olun
- Dosya boyutunun makul olduğunu kontrol edin
- Dosyanın bozuk olmadığından emin olun

### Analiz Sorunları
- Model yanıtının JSON formatında olduğunu kontrol edin
- Timeout süresini artırmayı deneyin
- Model parametrelerini ayarlayın

## 📈 Gelecek Özellikler

- [ ] Çoklu dosya desteği
- [ ] Analiz geçmişi kaydetme
- [ ] PDF rapor oluşturma
- [ ] Farklı AI modelleri desteği
- [ ] Veritabanı entegrasyonu
- [ ] Kullanıcı hesapları
- [ ] Batch işleme
- [ ] API endpoint'leri

## 🤝 Katkıda Bulunma

Bu proje açık kaynak olarak geliştirilmektedir. Katkılarınızı bekliyoruz!

## 📄 Lisans

Bu proje MIT lisansı altında lisanslanmıştır.

---

**Not**: Bu uygulama lokal AI modeli kullanır, bu nedenle verileriniz tamamen güvende kalır ve hiçbir dış servise gönderilmez.