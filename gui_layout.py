"""A főablak felépítése: felső sáv (monitor, preset, kapcsoló), fülek és alsó sáv. A függvények a létrehozott elemeket a
`panel.widgets` névtérbe teszik, a gombok és mezők eseményeit a `panel` metódusaihoz kötik; a viselkedést a `gui_panel.Panel`
adja."""
import sys

import customtkinter as ctk

from config import BACKUP_DIR
from consts import DATA_DIR, LOG_FILE
from gui_widgets import GREY_BUTTON, MUTED_TEXT, HotkeyEntry, RgbPicker, build_slider, section_title

TAB_IMAGE, TAB_COLORS, TAB_GAME, TAB_NIGHT, TAB_PROGRAM = "Kép", "Színek", "Játék és profil", "Éjszakai mód", "Program"
NO_POWER_PLAN = "Nem változtat"
HINT_WRAP = 520                                            # a magyarázó szövegek tördelési szélessége (képpont)
DIRTY_COLOR = ("#b45309", "#f59e0b")


def format_percent(value):
    return f"{value:.0f}%"


def format_gamma(value):
    return f"{value:.2f}"


def build_main_window(page, panel):
    """A `page` keretbe felépíti a teljes főablakot. Az elemek a `panel.widgets`-be kerülnek."""
    widgets = panel.widgets
    _build_top_bar(page, panel)
    widgets.tabs = ctk.CTkTabview(page, corner_radius=12)
    widgets.tabs.pack(fill="both", expand=True, pady=(10, 0))
    for tab_name in (TAB_IMAGE, TAB_COLORS, TAB_GAME, TAB_NIGHT, TAB_PROGRAM):
        widgets.tabs.add(tab_name)
    for tab_name, build_tab in ((TAB_IMAGE, _build_image_tab), (TAB_COLORS, _build_colors_tab), (TAB_GAME, _build_game_tab),
                                (TAB_NIGHT, _build_night_tab), (TAB_PROGRAM, _build_program_tab)):
        build_tab(_scrollable_body(widgets.tabs.tab(tab_name)), panel)      # kis ablaknál sem vágódik le a fül tartalma
    _build_bottom_bar(page, panel)
    widgets.tabs.pack_forget()                              # a fülek az alsó sáv UTÁN kapjanak helyet
    widgets.tabs.pack(fill="both", expand=True, pady=(10, 0))


def _scrollable_body(tab):
    """A fül teljes területét kitöltő, görgethető átlátszó keret; ebbe kerül a fül tartalma."""
    body = ctk.CTkScrollableFrame(tab, fg_color="transparent")
    body.pack(fill="both", expand=True)
    return body


def _transparent_frame(parent):
    return ctk.CTkFrame(parent, fg_color="transparent")


def _hint(parent, text, pady, wraplength=HINT_WRAP):
    """Halvány magyarázó szöveg balra igazítva."""
    ctk.CTkLabel(parent, text=text, text_color=MUTED_TEXT, wraplength=wraplength, justify="left").pack(anchor="w", pady=pady)


def _slider(panel, parent, caption, low, high, steps, format_value, default):
    return build_slider(parent, caption, low, high, steps, format_value, on_change=panel.on_slider, default=default)


def _grey_button(parent, text, width, command):
    return ctk.CTkButton(parent, text=text, width=width, command=command, **GREY_BUTTON)


def _build_top_bar(page, panel):
    widgets = panel.widgets
    top_bar = ctk.CTkFrame(page, corner_radius=12)
    top_bar.pack(fill="x")
    widgets.monitor_selector = ctk.CTkSegmentedButton(
        top_bar, values=[monitor["name"] for monitor in panel.eng.mons()],
        command=lambda name: panel.pick_monitor(name, ask=True))
    widgets.monitor_selector.pack(fill="x", padx=14, pady=(12, 8))
    preset_row = _transparent_frame(top_bar)                  # "Alkalmazás:" felirat + választó, középen
    preset_row.pack(pady=(6, 0))
    ctk.CTkLabel(preset_row, text="Alkalmazás:").pack(side="left")
    widgets.preset_menu = ctk.CTkOptionMenu(preset_row, values=["Alap"], width=260, anchor="center",
                                            command=panel.pick_preset)
    widgets.preset_menu.pack(side="left", padx=(8, 0))
    button_row = _transparent_frame(top_bar)                  # alatta a gombok egy sorban, középen
    button_row.pack(pady=(12, 0))
    actions = panel.preset_actions
    _grey_button(button_row, "Új…", 76, actions.new_preset).pack(side="left")
    _grey_button(button_row, "Másolás…", 90, actions.copy_preset).pack(side="left", padx=(8, 0))
    widgets.rename_preset_button = _grey_button(button_row, "Átnevezés…", 100, actions.rename_preset)
    widgets.rename_preset_button.pack(side="left", padx=(8, 0))
    widgets.delete_preset_button = _grey_button(button_row, "Törlés", 76, actions.delete_preset)
    widgets.delete_preset_button.pack(side="left", padx=(8, 0))
    widgets.enabled_switch = ctk.CTkSwitch(top_bar, text="Be van kapcsolva", command=panel.toggle_enabled)
    widgets.enabled_switch.pack(pady=(16, 16))               # a gombok alatt


def _build_image_tab(tab, panel):
    widgets = panel.widgets
    actions = panel.preset_actions
    variant_bar = _transparent_frame(tab)                     # változatok: a kiválasztott preset (alkalmazás) alatt
    variant_bar.pack(fill="x", pady=(8, 0))
    variant_row = _transparent_frame(variant_bar)             # a változat-választó középen
    variant_row.pack()
    ctk.CTkLabel(variant_row, text="Változat:").pack(side="left")
    widgets.variant_menu = ctk.CTkOptionMenu(variant_row, values=["–"], width=260, anchor="center",
                                             command=panel.pick_variant)
    widgets.variant_menu.pack(side="left", padx=(8, 0))
    variant_buttons = _transparent_frame(variant_bar)         # alatta a 3 gomb, szintén középen
    variant_buttons.pack(pady=(12, 0))
    _grey_button(variant_buttons, "Új…", 70, actions.new_variant).pack(side="left")
    widgets.rename_variant_button = _grey_button(variant_buttons, "Átnevezés…", 96, actions.rename_variant)
    widgets.rename_variant_button.pack(side="left", padx=(8, 0))
    widgets.delete_variant_button = _grey_button(variant_buttons, "Törlés", 70, actions.delete_variant)
    widgets.delete_variant_button.pack(side="left", padx=(8, 0))
    hotkey_row = _transparent_frame(tab)
    hotkey_row.pack(fill="x", pady=(22, 0))
    ctk.CTkLabel(hotkey_row, text="Gyorsgomb (erre a változatra):", width=190, anchor="w").pack(side="left")
    widgets.variant_hotkey = HotkeyEntry(hotkey_row)
    widgets.variant_hotkey.pack(side="left", padx=(8, 0))
    ctk.CTkFrame(tab, height=1, fg_color=("gray78", "gray28")).pack(fill="x", pady=(20, 4))      # elválasztó a csúszkák előtt
    widgets.brightness = _slider(panel, tab, "Fényerő", 0, 100, 100, format_percent, default=50)
    widgets.contrast = _slider(panel, tab, "Kontraszt", 0, 100, 100, format_percent, default=50)
    widgets.gamma = _slider(panel, tab, "Gamma", 0.30, 2.80, 250, format_gamma, default=1.0)    # mint az NVIDIA panelben
    widgets.vibrance = _slider(panel, tab, "Digital vibrance (NVIDIA)", 0, 100, 100, format_percent, default=50)
    widgets.vibrance_hint = ctk.CTkLabel(tab, text="", anchor="w", justify="left", wraplength=560, text_color=("gray40", "gray60"))
    widgets.image_buttons_row = _transparent_frame(tab)
    widgets.image_buttons_row.pack(fill="x", pady=(28, 0))
    widgets.defaults_button = _grey_button(widgets.image_buttons_row, "Preset alapértéke", 140, panel.load_preset_defaults)
    widgets.defaults_button.pack(side="left")
    _grey_button(widgets.image_buttons_row, "Semleges kép", 120, panel.show_neutral).pack(side="left", padx=(8, 0))
    widgets.compare_button = _grey_button(widgets.image_buttons_row, "Összehasonlítás (nyomva tartva)", 210, None)
    widgets.compare_button.pack(side="left", padx=(8, 0))
    widgets.compare_button.bind("<ButtonPress-1>", lambda event: panel.compare_with_neutral(True), add="+")
    widgets.compare_button.bind("<ButtonRelease-1>", lambda event: panel.compare_with_neutral(False), add="+")
    _hint(tab, "Amíg ez az ablak nyitva van, a csúszkák élőben hatnak, de mentés nélkül bezárva a mentett "
               "állapot tér vissza. A \"Be van kapcsolva\" kapcsoló ettől független: az marad, ami be van kapcsolva.\n"
               "Az érték a csúszka melletti mezőbe be is írható; dupla kattintás a csúszkán az alapértékre állítja.",
          pady=(20, 0))


def _build_colors_tab(tab, panel):
    """R/G/B csatornák erősítése (100% = semleges; csökkentve az adott szín halványodik)."""
    widgets = panel.widgets
    widgets.red_gain = _slider(panel, tab, "Vörös", 0, 100, 100, format_percent, default=100)
    widgets.green_gain = _slider(panel, tab, "Zöld", 0, 100, 100, format_percent, default=100)
    widgets.blue_gain = _slider(panel, tab, "Kék", 0, 100, 100, format_percent, default=100)
    _grey_button(tab, "Színek visszaállítása (100%)", 210, panel.reset_colors).pack(anchor="w", pady=(28, 0))
    _hint(tab, "Csatornánként csökkentheted az erősítést: kevesebb kékkel melegebb, kevesebb vörössel "
               "hidegebb a kép. 100% a semleges. A beállítás a kiválasztott változaté (vagy az alkalmazásé, ha nincs "
               "változata), és együtt mentődik a többivel; az éjszakai mód ráteszi a magáét.", pady=(20, 0))


def _build_game_tab(tab, panel):
    widgets = panel.widgets
    section_title(tab, "Automatikus bekapcsolás")
    process_row = _transparent_frame(tab)
    process_row.pack(fill="x")
    widgets.process_entry = ctk.CTkEntry(process_row, width=200, placeholder_text="a játék exe-ja, pl. bf6")
    widgets.process_entry.pack(side="left")
    _grey_button(process_row, "Futó programok…", 130, panel.choose_running_program).pack(side="left", padx=(8, 0))
    _grey_button(process_row, "Tallózás…", 90, panel.browse_executable).pack(side="left", padx=(8, 0))
    _hint(tab, "Ha ez a program elindul, a preset magától bekapcsol; kilépéskor kikapcsol. Üresen hagyva csak kézzel.",
          pady=(4, 0))
    section_title(tab, "Gyorsgomb (be- és kikapcsolja a presetet)")
    widgets.preset_hotkey = HotkeyEntry(tab)
    widgets.preset_hotkey.pack(anchor="w")
    section_title(tab, "Profil: amikor a preset bekapcsol…")
    power_row = _transparent_frame(tab)
    power_row.pack(fill="x")
    ctk.CTkLabel(power_row, text="Energiaprofil:", width=100, anchor="w").pack(side="left")
    plan_names = [plan_name for _, plan_name, _ in panel.power_plans]
    widgets.power_plan_menu = ctk.CTkOptionMenu(power_row, values=[NO_POWER_PLAN] + plan_names, width=240)
    widgets.power_plan_menu.pack(side="left")
    rgb_row = _transparent_frame(tab)
    rgb_row.pack(fill="x", pady=(8, 0))
    ctk.CTkLabel(rgb_row, text="RGB:", width=100, anchor="w").pack(side="left")
    widgets.rgb_picker = RgbPicker(rgb_row)
    widgets.rgb_picker.pack(side="left")
    _hint(tab, "Kikapcsoláskor az energiaprofil visszaáll az előzőre, az RGB pedig az \"alap\" állapotra "
               "(Program fül). A JBL EQ innen nem váltható, azt a JBL alkalmazás játékfelismerése kezeli.", pady=(8, 0))


def _build_night_tab(tab, panel):
    widgets = panel.widgets
    widgets.night_switch = ctk.CTkSwitch(tab, text="Éjszakai mód bekapcsolva", command=panel.toggle_night)
    widgets.night_switch.pack(anchor="w", pady=(10, 0))
    widgets.night_strength = _slider(panel, tab, "Erősség (melegebb, halványabb kép)", 0, 100, 100, format_percent, default=60)
    section_title(tab, "Gyorsgomb")
    widgets.night_hotkey = HotkeyEntry(tab, on_change=lambda text: panel.set_setting("night_hotkey", text))
    widgets.night_hotkey.pack(anchor="w")
    _hint(tab, "A kapcsoló monitoronként külön működik: mindig a fent kiválasztott monitort érinti (a tálcamenüben "
               "minden monitornál van külön, és van egy \"minden monitor\" is). A gyorsgomb az összes monitort "
               "együtt kapcsolja: ha bárhol be van kapcsolva, mindenhol kikapcsol.\n"
               "Csak akkor kapcsol be, ha te bekapcsolod; a program újraindításakor mindig kikapcsolt. Játék alatt "
               "(ha annak a presetje be van kapcsolva az adott monitoron) szünetel, hogy a színek ne torzuljanak.", pady=(14, 0))


def _build_program_tab(tab, panel):
    widgets = panel.widgets
    startup_target = "Windows-szal" if sys.platform == "win32" else "rendszerrel"
    widgets.autostart_switch = ctk.CTkSwitch(tab, text=f"Indítás a {startup_target} (tálcán, ablak nélkül)",
                                             command=panel.toggle_autostart)
    widgets.autostart_switch.pack(anchor="w", pady=(10, 0))
    widgets.toast_switch = ctk.CTkSwitch(tab, text="Értesítés a képernyőn váltáskor (a játék fölött is)",
                                         command=panel.toggle_toast_setting)
    widgets.toast_switch.pack(anchor="w", pady=(10, 0))
    toast_row = _transparent_frame(tab)
    toast_row.pack(fill="x", pady=(6, 0))
    _grey_button(toast_row, "Értesítés próbája", 140, panel.show_test_toast).pack(side="left")
    ctk.CTkLabel(toast_row, text="Teljes képernyős (exkluzív) módú játék fölött nem látszik; ablak nélküli módban igen.",
                 text_color=MUTED_TEXT, wraplength=360, justify="left").pack(side="left", padx=(10, 0))
    section_title(tab, "Gyorsgomb: változat léptetése (az éppen aktív játék következő változatára)")
    widgets.cycle_hotkey = HotkeyEntry(tab, on_change=lambda text: panel.set_setting("cycle_hotkey", text))
    widgets.cycle_hotkey.pack(anchor="w")
    _hint(tab, "Egy gomb minden játéknál: azon a monitoron, ahol aktív a preset, a következő változatra lép, "
               "az utolsó után újra az elsőre. Ha a presetnek nincsenek változatai, nem csinál semmit.", pady=(4, 0))
    section_title(tab, "Gyorsgomb: játék-overlay (az aktuális játék profilja a játék fölött)")
    widgets.overlay_hotkey = HotkeyEntry(tab, on_change=lambda text: panel.set_setting("overlay_hotkey", text))
    widgets.overlay_hotkey.pack(anchor="w")
    _hint(tab, "Ugyanaz a gomb nyitja és zárja. Nyitva: ↑↓ sor, ←→ állít (Shift: ×5), Del alapérték, Enter mentés, "
               "N új változat a mostani állásból, Esc elvet. Amíg nyitva van, ezek a gombok nem jutnak el a játékhoz.",
          pady=(4, 0))
    if sys.platform == "win32":
        section_title(tab, "Gyorsgomb: főmenü (Térkép, Böngésző, Képbeállítások)")
        widgets.menu_hotkey = HotkeyEntry(tab, on_change=lambda text: panel.set_setting("menu_hotkey", text))
        widgets.menu_hotkey.pack(anchor="w")
        _hint(tab, "Ugyanaz a gomb nyitja és zárja a játék fölött. Nyitva: ↑↓ választ, Enter megnyit, Esc zár; egérrel is "
                   "kattintható. Alapból Shift+Tab: a Képprofil futása alatt ezt a gombot a Képprofil használja, egyik program (a játék sem) kapja meg; ha másra kell, itt átállítható.",
              pady=(4, 0))
        section_title(tab, "Gyorsgomb: térkép elő-/eltüntetése (Escape from Tarkov)")
        widgets.map_hotkey = HotkeyEntry(tab, on_change=lambda text: panel.set_setting("map_hotkey", text))
        widgets.map_hotkey.pack(anchor="w")
        _hint(tab, "Áttetsző, átkattintható interaktív térkép a játék fölött. A pályát a Tarkov logjából ismeri fel, és a raid "
                   "betöltésekor magától megnyílik (alább kikapcsolható).", pady=(4, 0))
        section_title(tab, "Gyorsgomb: a térkép módjának léptetése")
        widgets.map_interact_hotkey = HotkeyEntry(
            tab, on_change=lambda text: panel.set_setting("map_interact_hotkey", text))
        widgets.map_interact_hotkey.pack(anchor="w")
        _hint(tab, "Pillantás → billentyűzet (←↑↓→ mozgat, numpad + és − nagyít, PageUp/PageDown az átlátszóságot állítja, Esc kilép; amíg ez a mód él, ezek a gombok nem "
                   "jutnak el a játékhoz) → egér (az ablak fókuszt kap, mozgatható, kattintható) → pillantás.", pady=(4, 0))
        widgets.map_auto_switch = ctk.CTkSwitch(tab, text="A térkép automatikus megnyitása a raid betöltésekor",
                                                command=panel.toggle_map_auto)
        widgets.map_auto_switch.pack(anchor="w", pady=(10, 0))
        widgets.map_alpha = _slider(panel, tab, "Térkép átlátszósága", 20, 100, 80, format_percent, default=85)
        widgets.learned_maps_label = ctk.CTkLabel(tab, text="", anchor="w", justify="left", wraplength=HINT_WRAP)
        widgets.learned_maps_label.pack(anchor="w", pady=(14, 0))
        widgets.forget_maps_button = _grey_button(tab, "Megtanult pályanevek törlése", 220, panel.forget_learned_maps)
        widgets.forget_maps_button.pack(anchor="w", pady=(4, 0))
        _hint(tab, "Ha a program nem ismeri fel a pályát, a térképablak tetején kézzel választhatsz; a választás megtanítja a "
                   "pálya logbeli nevét, így legközelebb magától felismeri. Itt törölheted a megtanultakat (például egy téves "
                   "választás után).", pady=(4, 0))
    section_title(tab, "Gyorsgomb: semleges kép (minden kikapcsol)")
    widgets.neutral_hotkey = HotkeyEntry(tab, on_change=lambda text: panel.set_setting("neutral_hotkey", text))
    widgets.neutral_hotkey.pack(anchor="w")
    section_title(tab, "RGB alapállapot (ide áll vissza, ha egy profil kikapcsol)")
    widgets.base_rgb_picker = RgbPicker(tab, on_change=lambda spec: panel.set_setting("base_rgb", spec))
    widgets.base_rgb_picker.pack(anchor="w")
    _grey_button(tab, "A mostani RGB-állapot mentése alapnak", 270, panel.save_current_rgb_as_base).pack(
        anchor="w", pady=(8, 0))
    section_title(tab, "Mentés és visszatöltés")
    backup_row = _transparent_frame(tab)
    backup_row.pack(fill="x")
    _grey_button(backup_row, "Exportálás…", 120, panel.preset_actions.export_all).pack(side="left")
    _grey_button(backup_row, "Importálás…", 120, panel.preset_actions.import_all).pack(side="left", padx=(8, 0))
    _hint(tab, f"Az összes preset és beállítás egy fájlba. A program naponta egyszer maga is másolatot készít "
               f"(utolsó 10 marad): {BACKUP_DIR}", pady=(6, 0))
    folder_row = _transparent_frame(tab)
    folder_row.pack(fill="x", pady=(14, 0))
    _grey_button(folder_row, "Napló megnyitása", 140, lambda: panel.open_in_system(LOG_FILE)).pack(side="left")
    _grey_button(folder_row, "Adatmappa megnyitása", 160, lambda: panel.open_in_system(DATA_DIR)).pack(
        side="left", padx=(8, 0))
    widgets.info_label = ctk.CTkLabel(tab, text="", text_color=MUTED_TEXT, wraplength=HINT_WRAP, justify="left")
    widgets.info_label.pack(anchor="w", pady=(14, 0))


def _build_bottom_bar(page, panel):
    widgets = panel.widgets
    bottom_bar = _transparent_frame(page)
    bottom_bar.pack(side="bottom", fill="x", pady=(10, 0))   # alulra rögzítve: kis ablaknál sem csúszhat ki
    ctk.CTkButton(bottom_bar, text="Mentés a presetbe", width=160, command=panel.save_preset).pack(side="left")
    widgets.dirty_label = ctk.CTkLabel(bottom_bar, text="", text_color=DIRTY_COLOR, width=150, anchor="w")   # mentetlen módosítás
    widgets.dirty_label.pack(side="left", padx=(12, 0))
    widgets.status_label = ctk.CTkLabel(bottom_bar, text="", text_color=MUTED_TEXT, anchor="w", wraplength=240, justify="left")
    widgets.status_label.pack(side="left", padx=12)
