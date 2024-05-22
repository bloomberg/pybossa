valid_user_preferences = {}


def upref_languages():
    langs = [
        ("Afrikaans", "Afrikaans"),
        ("Albanian", "Albanian"),
        ("Arabic", "Arabic"),
        ("Armenian", "Armenian"),
        ("Bengali", "Bengali"),
        ("Bosnian", "Bosnian"),
        ("Bulgarian", "Bulgarian"),
        ("Catalan", "Catalan"),
        ("Croatian", "Croatian"),
        ("Czech", "Czech"),
        ("Danish", "Danish"),
        ("Dutch", "Dutch"),
        ("English", "English"),
        ("Estonian", "Estonian"),
        ("Filipino", "Filipino"),
        ("Finnish", "Finnish"),
        ("French", "French"),
        ("German", "German"),
        ("Greek", "Greek"),
        ("Hebrew", "Hebrew"),
        ("Hindi", "Hindi"),
        ("Hungarian", "Hungarian"),
        ("Icelandic", "Icelandic"),
        ("Indonesian", "Indonesian"),
        ("Italian", "Italian"),
        ("Japanese", "Japanese"),
        ("Korean", "Korean"),
        ("Latvian", "Latvian"),
        ("Lithuanian", "Lithuanian"),
        ("Luxembourgish", "Luxembourgish"),
        ("Macedonian", "Macedonian"),
        ("Malay", "Malay"),
        ("Maltese", "Maltese"),
        ("Mongolian", "Mongolian"),
        ("Norwegian", "Norwegian"),
        ("Polish", "Polish"),
        ("Portuguese", "Portuguese"),
        ("Punjabi", "Punjabi"),
        ("Romanian", "Romanian"),
        ("Russian", "Russian"),
        ("Samoan", "Samoan"),
        ("Serbian", "Serbian"),
        ("Simplified Chinese", "Simplified Chinese"),
        ("Slovak", "Slovak"),
        ("Slovenian", "Slovenian"),
        ("Spanish", "Spanish"),
        ("Swedish", "Swedish"),
        ("Tamil", "Tamil"),
        ("Thai", "Thai"),
        ("Traditional Chinese", "Traditional Chinese"),
        ("Turkish", "Turkish"),
        ("Ukrainian", "Ukrainian"),
        ("Vietnamese", "Vietnamese"),
        ("Welsh", "Welsh"),
    ]
    return langs


countries = ["Bonaire", "Kiribati", "Vanuatu", "Wallis and Futuna"]


def upref_locations():
    cts = []
    for ct in countries:
        cts.append((ct, ct))
    return sorted(cts)


def mdata_user_types():
    types = [
        ("", ""),
        ("Researcher", "Researcher"),
        ("Analyst", "Analyst"),
        ("Curator", "Curator"),
    ]

    return types


def mdata_timezones():
    tz = [
        ("", ""),
        ("ACT", "Australia Central Time"),
        ("AET", "Australia Eastern Time"),
        ("AGT", "Argentina Standard Time"),
        ("ART", "(Arabic) Egypt Standard Time"),
        ("AST", "Alaska Standard Time"),
        ("BET", "Brazil Eastern Time"),
        ("BST", "Bangladesh Standard Time"),
        ("CAT", "Central African Time"),
        ("CNT", "Canada Newfoundland Time"),
        ("CST", "Central Standard Time"),
        ("CTT", "China Taiwan Time"),
        ("EAT", "Eastern African Time"),
        ("ECT", "European Central Time"),
        ("EET", "Eastern European Time"),
        ("EST", "Eastern Standard Time"),
        ("GMT", "Greenwich Mean Time"),
        ("HST", "Hawaii Standard Time"),
        ("IET", "Indiana Eastern Standard Time"),
        ("IST", "India Standard Time"),
        ("JST", "Japan Standard Time"),
        ("MET", "Middle East Time"),
        ("MIT", "Midway Islands Time"),
        ("MST", "Mountain Standard Time"),
        ("NET", "Near East Time"),
        ("NST", "New Zealand Standard Time"),
        ("PLT", "Pakistan Lahore Time"),
        ("PNT", "Phoenix Standard Time"),
        ("PRT", "Puerto Rick and US Virgin Islands Time"),
        ("PST", "Pacific Standard Time"),
        ("SST", "Solomon Standard Time"),
        ("UTC", "Universal Coordinated Time"),
        ("VST", "Vietnam Standard Time"),
    ]
    return tz


def get_upref_mdata_choices():
    upref_mdata_choices = dict(
        languages=upref_languages(),
        locations=upref_locations(),
        timezones=mdata_timezones(),
        user_types=mdata_user_types(),
    )
    return upref_mdata_choices


def get_valid_user_preferences():
    if not valid_user_preferences:
        upref_mdata_choices = get_upref_mdata_choices()
        for user_pref, values in upref_mdata_choices.items():
            valid_user_preferences[user_pref] = [v[0] for v in values]
    return valid_user_preferences
