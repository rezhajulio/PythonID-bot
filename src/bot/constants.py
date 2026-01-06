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
    "untuk mematuhi aturan grup.\n"
    "Kamu akan dibatasi setelah {threshold_display}.\n\n"
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
    "✉️ [Hubungi langsung robot untuk membuka pembatasan (mohon pertimbangkan bahwa percakapan dengan robot saat ini sebagian besar belum direkam)]({dm_link})"
)

# Restriction message when user reaches time threshold (scheduler)
RESTRICTION_MESSAGE_AFTER_TIME = (
    "🚫 {user_mention} telah dibatasi karena tidak melengkapi profil "
    "dalam {threshold_display}.\n\n"
    "📖 [Baca aturan grup]({rules_link})\n"
    "✉️ [Hubungi langsung robot untuk membuka pembatasan (mohon pertimbangkan bahwa percakapan dengan robot saat ini sebagian besar belum direkam)]({dm_link})"
)

# Captcha verification message templates
CAPTCHA_WELCOME_MESSAGE = (
    "👋 Selamat datang {user_mention}!\n\n"
    "Untuk memastikan kamu bukan robot, silakan klik tombol di bawah ini "
    "dalam waktu {timeout} detik."
)

CAPTCHA_VERIFIED_MESSAGE = "✅ Terima kasih {user_mention}, verifikasi berhasil! Selamat bergabung."

CAPTCHA_WRONG_USER_MESSAGE = "❌ Tombol ini bukan untukmu."

CAPTCHA_TIMEOUT_MESSAGE = (
    "🚫 {user_mention} tidak menyelesaikan verifikasi dalam waktu yang ditentukan.\n\n"
    "Silakan {dm_link} untuk membuka pembatasan."
)

CAPTCHA_PENDING_DM_MESSAGE = (
    "⏳ Kamu memiliki verifikasi captcha yang tertunda.\n"
    "Silakan cek grup dan tekan tombol verifikasi."
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

ADMIN_CHECK_PROMPT = (
    "📋 User: {user_mention} (ID: `{user_id}`)\n\n"
    "Status Profil:\n"
    "• Foto Profil: {photo_status}\n"
    "• Username: {username_status}\n\n"
    "{action_prompt}"
)

ADMIN_CHECK_ACTION_COMPLETE = "✅ Profil lengkap, tidak ada aksi yang diperlukan."

ADMIN_CHECK_ACTION_INCOMPLETE = "⚠️ Profil tidak lengkap. Pilih aksi:"

ADMIN_WARN_USER_MESSAGE = (
    "⚠️ Hai {user_mention}, mohon lengkapi {missing_text} kamu "
    "untuk mematuhi aturan grup.\n\n"
    "📖 [Baca aturan grup]({rules_link})"
)

ADMIN_WARN_SENT_MESSAGE = "✅ Peringatan telah dikirim ke {user_mention} di grup."

# Anti-spam probation warning for new users
NEW_USER_SPAM_WARNING = (
    "⚠️ {user_mention} baru bergabung dan sedang dalam masa percobaan.\n"
    "Selama {probation_display}, kamu tidak boleh meneruskan pesan atau mengirim tautan.\n"
    "Pesan yang melanggar akan dihapus dan kamu bisa dibatasi jika terus mengulang.\n"
    "Hubungi admin jika kamu membutuhkan bantuan.\n\n"
    "📖 [Baca aturan grup]({rules_link})"
)

# Anti-spam restriction message when user exceeds violation threshold
NEW_USER_SPAM_RESTRICTION = (
    "🚫 {user_mention} telah dibatasi karena mengirim pesan terlarang "
    "(forward/link/quote eksternal) sebanyak {violation_count} kali selama masa percobaan.\n\n"
    "📖 [Baca aturan grup]({rules_link})"
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
