"""
Application constants for the PythonID bot.

This module contains shared constants used across multiple bot modules,
including permissions, message templates, and formatting utilities.
"""

from telegram import ChatPermissions

# Permissions applied when restricting a user (effectively mutes them)
RESTRICTED_PERMISSIONS = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
    can_change_info=False,
    can_invite_users=False,
    can_pin_messages=False,
    can_manage_topics=False,
)

# Missing items separator for Indonesian language
MISSING_ITEMS_SEPARATOR = " dan "


def format_threshold_display(threshold_minutes: int) -> str:
    """
    Format time threshold in minutes to human-readable Indonesian text.
    
    Converts minutes to "X jam" for values >= 60, or "Y menit" for smaller values.
    
    Args:
        threshold_minutes: Time threshold in minutes.
        
    Returns:
        Formatted string like "3 jam" or "30 menit".
    """
    if threshold_minutes >= 60:
        hours = threshold_minutes // 60
        return f"{hours} jam"
    return f"{threshold_minutes} menit"


def format_hours_display(hours: int) -> str:
    """
    Format hours to human-readable Indonesian text.
    
    Converts hours to "X hari" for values >= 24, or "Y jam" for smaller values.
    
    Args:
        hours: Time in hours.
        
    Returns:
        Formatted string like "7 hari" or "12 jam".
    """
    if hours >= 24:
        days = hours // 24
        return f"{days} hari"
    return f"{hours} jam"


# Message templates used in warning and restriction scenarios
# Warning mode (default): No restrictions, just warnings
WARNING_MESSAGE_NO_RESTRICTION = (
    "⚠️ Hai {user_mention}, mohon lengkapi {missing_text} kamu "
    "untuk mematuhi aturan grup.\n\n"
    "📖 [Baca aturan grup]({rules_link})"
)

# Progressive restriction mode: First message warning
WARNING_MESSAGE_WITH_THRESHOLD = (
    "⚠️ Hai {user_mention}, mohon lengkapi {missing_text} kamu "
    "untuk mematuhi aturan grup.\n"
    "Kamu akan dibatasi setelah {warning_threshold} pesan atau {threshold_display}.\n\n"
    "📖 [Baca aturan grup]({rules_link})"
)

# Restriction message when user reaches message threshold
RESTRICTION_MESSAGE_AFTER_MESSAGES = (
    "🚫 {user_mention} telah dibatasi setelah {message_count} pesan.\n"
    "Mohon lengkapi {missing_text} kamu untuk mematuhi aturan grup.\n\n"
    "📖 [Baca aturan grup]({rules_link})\n"
    "✉️ [Hubungi langsung robot untuk membuka pembatasan]({dm_link}) "
    "(mohon pertimbangkan bahwa percakapan dengan robot saat ini sebagian besar belum direkam)"
)

# Restriction message when user reaches time threshold (scheduler)
RESTRICTION_MESSAGE_AFTER_TIME = (
    "🚫 {user_mention} telah dibatasi karena tidak melengkapi profil "
    "dalam {threshold_display}.\n\n"
    "📖 [Baca aturan grup]({rules_link})\n"
    "✉️ [Hubungi langsung robot untuk membuka pembatasan]({dm_link}) "
    "(mohon pertimbangkan bahwa percakapan dengan robot saat ini sebagian besar belum direkam)"
)

# Captcha verification message templates
CAPTCHA_WELCOME_MESSAGE = (
    "👋 Selamat datang {user_mention}!\n\n"
    "Sebelum bergabung, pastikan kamu sudah memiliki *foto profil publik* dan *username*.\n"
    "Setelah melengkapi profil, tekan tombol di bawah ini dalam waktu {timeout} detik."
)

CAPTCHA_VERIFIED_MESSAGE = "✅ Terima kasih {user_mention}, verifikasi berhasil! Selamat bergabung."

CAPTCHA_WRONG_USER_MESSAGE = "❌ Tombol ini bukan untukmu."

CAPTCHA_TIMEOUT_MESSAGE = (
    "🚫 {user_mention} tidak menyelesaikan verifikasi dalam waktu yang ditentukan.\n\n"
    "Silakan {dm_link} untuk membuka pembatasan."
)

CAPTCHA_PENDING_DM_MESSAGE = (
    "⏳ Kamu memiliki verifikasi captcha yang tertunda di grup berikut:\n{group_list}\n\n"
    "Silakan cek grup dan tekan tombol verifikasi."
)

CAPTCHA_PENDING_DM_GROUP_LINE = "• Grup {group_id}"

CAPTCHA_INCOMPLETE_PROFILE_MESSAGE = (
    "❌ Lengkapi {missing_text} terlebih dahulu, lalu tekan tombol ini lagi."
)

CAPTCHA_PROFILE_CHECK_FAILED_MESSAGE = (
    "❌ Gagal memeriksa profil. Coba lagi dalam beberapa detik."
)

CAPTCHA_FAILED_VERIFICATION_MESSAGE = "Gagal memverifikasi. Silakan coba lagi."

# DM handler message templates
DM_NOT_IN_GROUP_MESSAGE = (
    "❌ Kamu belum bergabung di grup.\n"
    "Silakan bergabung ke grup terlebih dahulu."
)

DM_INCOMPLETE_PROFILE_MESSAGE = (
    "❌ Kamu belum memenuhi persyaratan.\n\n"
    "Mohon lengkapi {missing_text} kamu terlebih dahulu, "
    "lalu kirim pesan lagi ke bot ini.\n\n"
    "📖 [Baca aturan grup]({rules_link})"
)

DM_NO_RESTRICTION_MESSAGE = (
    "ℹ️ Kamu tidak memiliki pembatasan dari bot ini.\n"
    "Jika kamu dibatasi oleh admin, silakan hubungi admin grup secara langsung."
)

DM_ALREADY_UNRESTRICTED_MESSAGE = (
    "ℹ️ Kamu sudah tidak dibatasi di grup.\n"
    "Silakan bergabung kembali!"
)

DM_UNRESTRICTION_SUCCESS_MESSAGE = (
    "✅ Selamat! Kamu sudah memenuhi persyaratan.\n"
    "Pembatasan kamu di grup telah dicabut. Silakan bergabung kembali!"
)

DM_UNRESTRICTION_NOTIFICATION = (
    "✅ {user_mention} telah melengkapi profil dan dicabut pembatasannya via DM."
)

VERIFICATION_CLEARANCE_MESSAGE = (
    "✅ {user_mention} telah diverifikasi oleh admin. Silakan berdiskusi kembali."
)

VERIFY_SUCCESS_MESSAGE = (
    "✅ User dengan ID {user_id} telah diverifikasi:\n"
    "• Ditambahkan ke whitelist foto profil\n"
    "• Riwayat warning dihapus di grup {group_id}\n\n"
    "User ini tidak akan dicek foto profil lagi."
)

VERIFY_SUCCESS_WITH_UNRESTRICT_MESSAGE = (
    "✅ User dengan ID {user_id} telah diverifikasi:\n"
    "• Ditambahkan ke whitelist foto profil\n"
    "• Pembatasan bot dicabut di grup {group_id}\n"
    "• Riwayat warning dihapus\n\n"
    "User ini tidak akan dicek foto profil lagi."
)

UNVERIFY_SUCCESS_MESSAGE = (
    "✅ User dengan ID {target_user_id} telah dihapus dari whitelist verifikasi foto."
)

UNRESTRICT_SUCCESS_MESSAGE = (
    "✅ Pembatasan bot untuk user `{user_id}` telah dicabut di grup {group_id}."
)

UNRESTRICT_FAILED_MESSAGE = (
    "❌ Gagal membuka pembatasan untuk user `{user_id}` di grup {group_id}. "
    "Pastikan bot memiliki izin yang cukup."
)

UNRESTRICT_NOT_NEEDED_MESSAGE = (
    "ℹ️ User `{user_id}` tidak dibatasi oleh bot di grup {group_id}."
)

ADMIN_CHECK_PROMPT = (
    "📋 User: {user_mention} (ID: `{user_id}`)\n\n"
    "Status Profil:\n"
    "• Foto Profil: {photo_status}\n"
    "• Username: {username_status}\n\n"
    "{action_prompt}"
)

ADMIN_CHECK_ACTION_COMPLETE = "✅ Profil lengkap, tidak ada aksi yang diperlukan."

ADMIN_CHECK_ACTION_INCOMPLETE = "⚠️ Profil tidak lengkap. Pilih aksi:"

ADMIN_CHECK_GROUP_PROMPT = (
    "📋 User: {user_mention} (ID: `{user_id}`)\n\n"
    "Status Profil:\n"
    "• Foto Profil: {photo_status}\n"
    "• Username: {username_status}\n\n"
    "Pilih grup untuk melakukan aksi:"
)

ADMIN_CHECK_GROUP_NONE = (
    "❌ Kamu bukan admin di grup mana pun yang dipantau oleh bot ini."
)

ADMIN_WARN_USER_MESSAGE = (
    "⚠️ Hai {user_mention}, mohon lengkapi {missing_text} kamu "
    "untuk mematuhi aturan grup.\n\n"
    "📖 [Baca aturan grup]({rules_link})"
)

ADMIN_WARN_SENT_MESSAGE = "✅ Peringatan telah dikirim ke {user_mention} di grup."

TRUST_USER_ID_REQUIRED_MESSAGE = (
    "❌ Penggunaan: /trust USER_ID atau /untrust USER_ID, atau forward pesan user ke bot."
)

TRUST_USER_ID_INVALID_MESSAGE = "❌ User ID harus berupa angka."

TRUST_ADDED_MESSAGE = (
    "✅ User `{user_id}` ditambahkan ke trusted list (kecualikan dari anti-spam).\n"
    "• Probation dibersihkan di {probation_clear_count} grup\n\n"
    "Catatan: Trust tidak membuka pembatasan. Gunakan tombol \"Buka pembatasan bot\" "
    "untuk mencabut pembatasan yang diterapkan oleh bot ini."
)

TRUST_ALREADY_EXISTS_MESSAGE = "ℹ️ User `{user_id}` sudah ada di trusted list."

TRUST_REMOVED_MESSAGE = "✅ User `{user_id}` dihapus dari trusted list."

TRUST_USER_NOT_FOUND_MESSAGE = "ℹ️ User `{user_id}` tidak ada di trusted list."

TRUST_LIST_EMPTY_MESSAGE = "ℹ️ Trusted list masih kosong."

TRUST_LIST_HEADER = "📋 Trusted Users:\n{trusted_lines}"

TRUST_DM_ONLY_MESSAGE = (
    "❌ Perintah ini hanya bisa digunakan di chat pribadi dengan bot."
)

TRUST_NO_PERMISSION_MESSAGE = (
    "❌ Kamu tidak memiliki izin untuk menggunakan perintah ini."
)

TRUST_CALLBACK_INVALID_MESSAGE = "❌ Data callback tidak valid."

TRUST_NO_GROUP_PERMISSION_MESSAGE = (
    "❌ Kamu bukan admin di grup ini."
)

CHECK_TRUST_BUTTON_LABEL = "🛡️ Kecualikan dari anti-spam"

CHECK_UNTRUST_BUTTON_LABEL = "🛡️ Cabut pengecualian anti-spam"

CHECK_VERIFY_BUTTON_LABEL = "📷 Izinkan foto tersembunyi"

CHECK_UNVERIFY_BUTTON_LABEL = "❌ Cabut izin foto"

CHECK_UNRESTRICT_BUTTON_LABEL = "🔓 Buka pembatasan bot"

CHECK_WARN_BUTTON_LABEL = "⚠️ Beri peringatan"

# Anti-spam probation warning for new users
NEW_USER_SPAM_WARNING = (
    "⚠️ {user_mention} baru bergabung dan sedang dalam masa percobaan.\n"
    "Selama {probation_display}, kamu tidak boleh mengirim media (foto, video, audio, dll.), meneruskan pesan, atau mengirim tautan.\n"
    "Pesan yang melanggar akan dihapus dan kamu bisa dibatasi jika terus mengulang.\n"
    "Hubungi admin jika kamu membutuhkan bantuan.\n\n"
    "📖 [Baca aturan grup]({rules_link})"
)

# Anti-spam restriction message when user exceeds violation threshold
NEW_USER_SPAM_RESTRICTION = (
    "🚫 {user_mention} telah dibatasi karena mengirim pesan terlarang "
    "(media/file/forward/link/quote eksternal) sebanyak {violation_count} kali selama masa percobaan.\n\n"
    "📖 [Baca aturan grup]({rules_link})"
)

# Inline keyboard spam notification
INLINE_KEYBOARD_SPAM_NOTIFICATION = (
    "🚫 *Spam Terdeteksi*\n\n"
    "Pesan dari {user_mention} telah dihapus karena mengandung "
    "tombol inline keyboard dengan tautan mencurigakan.\n\n"
    "Pengguna telah dibatasi.\n\n"
    "📌 [Peraturan Grup]({rules_link})"
)

INLINE_KEYBOARD_SPAM_NOTIFICATION_NO_RESTRICT = (
    "🚫 *Spam Terdeteksi*\n\n"
    "Pesan dari {user_mention} telah dihapus karena mengandung "
    "tombol inline keyboard dengan tautan mencurigakan.\n\n"
    "📌 [Peraturan Grup]({rules_link})"
)

# Contact spam notification
CONTACT_SPAM_NOTIFICATION = (
    "🚫 *Kontak Dihapus*\n\n"
    "Pesan kontak dari {user_mention} telah dihapus karena berbagi kontak/"
    "nomor telepon tidak diperbolehkan di grup ini.\n\n"
    "Pengguna telah dibatasi.\n\n"
    "📌 [Peraturan Grup]({rules_link})"
)

CONTACT_SPAM_NOTIFICATION_NO_RESTRICT = (
    "🚫 *Kontak Dihapus*\n\n"
    "Pesan kontak dari {user_mention} telah dihapus karena berbagi kontak/"
    "nomor telepon tidak diperbolehkan di grup ini.\n\n"
    "📌 [Peraturan Grup]({rules_link})"
)

# Duplicate message spam notification
DUPLICATE_SPAM_RESTRICTION = (
    "🚫 *Spam Pesan Duplikat*\n\n"
    "{user_mention} telah dibatasi karena mengirim pesan yang sama "
    "sebanyak {count} kali dalam waktu singkat.\n\n"
    "📌 [Peraturan Grup]({rules_link})"
)

DUPLICATE_SPAM_RESTRICTION_NO_RESTRICT = (
    "🚫 *Spam Pesan Duplikat*\n\n"
    "Pesan duplikat dari {user_mention} telah dihapus "
    "({count} pesan yang sama dalam waktu singkat).\n\n"
    "📌 [Peraturan Grup]({rules_link})"
)

# Bio bait spam notification (e.g. "cek bio aku" / "lihat byoh")
BIO_BAIT_SPAM_NOTIFICATION = (
    "🚫 *Spam Bio Bait Terdeteksi*\n\n"
    "Pesan dari {user_mention} telah dihapus karena berisi ajakan "
    "untuk mengecek bio/profil, pola yang umum dipakai untuk spam/promosi/scam.\n\n"
    "Pengguna telah dibatasi.\n\n"
    "📌 [Peraturan Grup]({rules_link})"
)

BIO_BAIT_SPAM_NOTIFICATION_NO_RESTRICT = (
    "🚫 *Spam Bio Bait Terdeteksi*\n\n"
    "Pesan dari {user_mention} telah dihapus karena berisi ajakan "
    "untuk mengecek bio/profil, pola yang umum dipakai untuk spam/promosi/scam.\n\n"
    "📌 [Peraturan Grup]({rules_link})"
)

# Bio profile link spam (user's profile bio contains promo/scam links)
BIO_LINK_SPAM_NOTIFICATION = (
    "🚫 *Spam Bio Profil Terdeteksi*\n\n"
    "Pesan dari {user_mention} telah dihapus karena akun ini memiliki "
    "bio profil dengan tautan/mention Telegram mencurigakan.\n\n"
    "Pengguna telah dibatasi.\n\n"
    "📌 [Peraturan Grup]({rules_link})"
)

BIO_LINK_SPAM_NOTIFICATION_NO_RESTRICT = (
    "🚫 *Spam Bio Profil Terdeteksi*\n\n"
    "Pesan dari {user_mention} telah dihapus karena akun ini memiliki "
    "bio profil dengan tautan/mention Telegram mencurigakan.\n\n"
    "📌 [Peraturan Grup]({rules_link})"
)

# Monitor-only alert for owner/admin chat when bio bait match is detected.
# Sent without parse_mode to preserve raw message/bio content for forensic review.
BIO_BAIT_MONITOR_ALERT = (
    "[BIO BAIT MONITOR]\n"
    "Reason: {reason}\n"
    "Group ID: {group_id}\n"
    "User ID: {user_id}\n"
    "User: {user_name}\n"
    "Username: {username}\n"
    "Message:\n{message_text}\n\n"
    "Profile Bio:\n{profile_bio}"
)

# Whitelisted URL domains for new user probation
# These domains are allowed even during probation period
# Matches exact domain or subdomains (e.g., "github.com" matches "www.github.com")
WHITELISTED_URL_DOMAINS = frozenset([
    # Documentation & References
    "docs.python.org",
    "docs.djangoproject.com",
    "flask.palletsprojects.com",
    "fastapi.tiangolo.com",
    "pydantic-docs.helpmanual.io",
    "pydantic.dev",
    "sqlalchemy.org",
    "docs.sqlalchemy.org",
    "pandas.pydata.org",
    "numpy.org",
    "scipy.org",
    "matplotlib.org",
    "scikit-learn.org",
    "pytorch.org",
    "tensorflow.org",
    "keras.io",
    "huggingface.co",
    "openai.com",
    "anthropic.com",
    "langchain.com",
    "docs.aws.amazon.com",
    "cloud.google.com",
    "docs.microsoft.com",
    "learn.microsoft.com",
    
    # Code Hosting & Collaboration
    "github.com",
    "gitlab.com",
    "bitbucket.org",
    "gist.github.com",
    "raw.githubusercontent.com",
    
    # Package Repositories
    "pypi.org",
    "anaconda.org",
    "conda.io",
    "hub.docker.com",
    
    # Community & Learning
    "stackoverflow.com",
    "stackexchange.com",
    "reddit.com",
    "medium.com",
    "towardsdatascience.com",
    "dev.to",
    "realpython.com",
    "pythonweekly.com",
    "kaggle.com",
    "colab.research.google.com",
    
    # Data Science & ML Resources
    "arxiv.org",
    "paperswithcode.com",
    "wandb.ai",
    "mlflow.org",
    "streamlit.io",
    "gradio.app",
    "jupyter.org",
    "nbviewer.jupyter.org",
    
    # API Documentation
    "developers.google.com",
    "developer.twitter.com",
    "developer.github.com",
    "api.telegram.org",
    "core.telegram.org",
    
    # Indonesian Tech Communities
    "dicoding.com",
])

# Whitelisted Telegram paths/usernames for new user probation
# Only these specific t.me paths are allowed (exact match on first path segment)
# e.g., "PythonID" allows "t.me/PythonID", "t.me/PythonID/123", but not "t.me/PythonIDSpam"
# Values should be lowercased for case-insensitive matching
WHITELISTED_TELEGRAM_PATHS = frozenset([    
    # Cloud & Platforms
    "juaragcp",
    "awsdatausergroupid",
    "awsusergroupid",
    "azureindo",
    "gcpuserid",
    "gcp_id",
    
    # AI & Data Science
    "artificialintelligence_indonesia",
    "businessintelligenceid",
    "dataengineeringid",
    "datascienceindonesia",
    "iaiforum",
    "machinelearningid",
    "nlp_lounge",
    "pytorchid",
    "scrapeid",
    "tableauprofessionals",
    "tensorflowid",
    
    # Databases
    "sqlserverid",
    "mongodb_id",
    "mongo_db",
    "mysqlid",
    "postgresql_id",
    
    # General Programming & Developer Groups
    "bandungdevcom",
    "belajarcoding",
    "belajarngodingbareng",
    "gnurindonesia",
    "belajargolangmariadb",
    "belajarhtmlcss",
    "bogordev",
    "borneokoding",
    "tgbotid",
    "otodidak_ngoding",
    "crbdev",
    "codingfess",
    "cscript",
    "femalegeek",
    "freekelasgithub",
    "frontendid",
    "gresikdev",
    "iamindonesia",
    "idstack",
    "infotechprogrammer",
    "itnusantara",
    "djemberdev",
    "kabayan_coding",
    "kelasmobilemalang",
    "backendid",
    "komunitasbk",
    "komunitasrpaindonesia",
    "kongkowitmedan",
    "kongkowitpekanbaru",
    "kotakodebetachat",
    "kulkultech",
    "odooindonesia",
    "pasuruandev",
    "programersemarangraya",
    "rantaudev",
    "santrenkoding",
    "sarccomuniverse",
    "sidoarjodev",
    "sinaudev",
    "soft_eng_id",
    "sparkarindonesia",
    "surabayadev",
    "lamongandev",
    "tamankodekode",
    "tiadevcommunity",
    "teknologi_umum_v2",
    "idwordpress",
    "smk_dev",
    
    # DevOps & Infrastructure
    "ansibleid",
    "cloudcomputingindonesia",
    "dockeridn",
    "iddevops",
    "kubernetesindonesia",
    "okdindonesia",
    "devopsjogja",
    
    # Firebase
    "firebaseindonesia",
    
    # FreeBSD
    "setanmerahid",
    
    # Game Development
    "gamerang",
    "gdevelopid",
    "godot_indonesia",
    "lombokgamedev",
    
    # IoT
    "kelasrobotgrup",
    "arduinoindonesiancommunity",
    "edukasielektronika",
    "raspberrypi_id",
    
    # iOS
    "ikaskus",
    "initialestore",
    "libimobiledevice",
    
    # Jokes
    "linux_memes",
    "programmerjokes",
    
    # Linux
    "archlinuxid",
    "artixlinux_id",
    "gnulinuxindonesia",
    "belajarlinuxbareng",
    "blankonlinux",
    "centosid",
    "debianid",
    "deepin_indonesia",
    "dotfiles_id",
    "elementaryid",
    "fedoraid",
    "gnomeid",
    "gnuweeb",
    "kalilinuxid",
    "kdeid",
    "linuxmalang",
    "linuxjember",
    "lfsid",
    "langitketujuh_id",
    "mint_id",
    "linuxgroupid",
    "manjaroid",
    "nixosid",
    "opensuse_id",
    "linuxsolo",
    "parrotsecurityindonesia",
    "rhel_id",
    "ubuntu_indo",
    "voidlinux_id",
    
    # macOS
    "macosid",
    
    # Office Productivity
    "excelid",
    "belajarlibreofficeindonesia",
    
    # Open Source & Security
    "osint_indonesia",
    "doscomedia",
    "forensicaid",
    "itsecurityindonesia",
    "linuxhackingid",
    "orangsiber",
    "reversingid",
    "cybersecurity_id",
    "hacktheboxindo",
    
    # Programming Languages (Specific)
    "dotnetusergroup",
    "dotnetcore_id",
    "xamarinindonesia",
    "androiddevbdg",
    "androiddevelopernasional",
    "teknorialcom",
    "android_lombok",
    "androiddevsurabaya",
    "jcomposeindonesia",
    "androidsemarang",
    "source_code_android",
    "yacgroup",
    "agilecirclesid",
    "agileindonesia",
    "assemblyid",
    "bashidorg",
    "ccpp_indonesia",
    "idcplc",
    "crystalid",
    "dart_web",
    "flutter_id",
    "flutter_jkt",
    "fluttermakassar",
    "lombokflutter",
    "elixir_id",
    "gophers_id",
    "golangjogja",
    "golangsurabaya",
    "rustacean_id",
    "jvmindonesia",
    "adonisid",
    "angularid",
    "deno_id",
    "indonesiaionic",
    "js_id",
    "jogjajs",
    "lombokjs",
    "nativescript_id",
    "nestjs_indonesia",
    "nextjs_id",
    "nodejsid",
    "bun_id",
    "react_idn",
    "reactnativeindo",
    "surabayajs",
    "svelte_id",
    "vuejsindonesia",
    "kotlin_crb",
    "kotlinindonesia",
    "delphiindonesia",
    "pascalid",
    "codeigniterindonesia",
    "laravelindonesia",
    "phpidforbusiness",
    "phpidforstudent",
    "phpjogloraya",
    "symfonyid",
    "botphp",
    "yiiframeworkindonesia",
    "bandung_py",
    "djangoid",
    "fastapiid",
    "flaskid",
    "lombok_py",
    "mkspy",
    "pyjogja",
    "pythonid", # Duplicate of "pythonid" but kept for completeness of list
    "python",
    "pythonlearnerr",
    "python_learners_group",
    "surabayapy",
    "railsid",
    "ruby_id",
    "swiftid",
    "typescriptindonesia",
    "sapabapindonesia",
    "gis_id",
    "leafletid",
    "qgisindonesia",
    
    # QA
    "sqa_id",
    "qamalang",
    
    # Text Editors
    "emacsid",
    "vimid",
])
