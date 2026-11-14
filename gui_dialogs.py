"""Önálló párbeszédablakok: a futó programok listája (játék kiválasztásához) és a gyorsbillentyű-súgó (Linux)."""
import customtkinter as ctk

from gui_widgets import GREY_BUTTON
from hw_common import build_action
from system import action_command, open_shortcut_settings, visible_programs

COPIED_RESET_MS = 1500            # ennyi ideig látszik a gombon a „Másolva" felirat


def choose_running_program(root, on_choose):
    """Megnyitja a futó programok listáját. A „Kiválaszt" gombra `on_choose(program_neve)` fut, ha van kijelölt elem."""
    window = ctk.CTkToplevel(root)
    window.title("Futó programok")
    window.geometry("460x460")
    window.transient(root)
    window.after(150, window.grab_set)
    ctk.CTkLabel(window, text="Indítsd el a játékot, majd válaszd ki a listából:").pack(anchor="w", padx=16, pady=(14, 6))
    program_list = ctk.CTkScrollableFrame(window)
    program_list.pack(fill="both", expand=True, padx=16)
    chosen = ctk.StringVar(value="")
    for program, title in visible_programs().items():
        ctk.CTkRadioButton(program_list, text=f"{program}   —   {title[:48]}", variable=chosen, value=program).pack(
            anchor="w", pady=3)

    def accept():
        if chosen.get():
            on_choose(chosen.get())
        window.destroy()

    footer = ctk.CTkFrame(window, fg_color="transparent")
    footer.pack(fill="x", padx=16, pady=12)
    ctk.CTkButton(footer, text="Kiválaszt", width=100, command=accept).pack(side="right")
    ctk.CTkButton(footer, text="Mégse", width=90, command=window.destroy, **GREY_BUTTON).pack(side="right", padx=8)


def shortcut_rows(eng):
    """A gyorsbillentyű-súgó sorai: `(felirat, akció)` párok. Az akció `None` is lehet (ilyet a megjelenítés kihagy)."""
    rows = [("Éjszakai mód (minden monitor)", "night"), ("Semleges kép (minden kikapcsol)", "neutral"),
            ("Következő változat (az aktív játéknál, minden monitoron)", "cycle")]
    for monitor in eng.mons():
        for preset_name, preset in monitor["presets"].items():
            rows.append((f"{monitor['name']} – {preset_name}", build_action("preset", monitor["id"], preset_name)))
            for variant_name in preset.get("variants") or {}:
                rows.append((f"{monitor['name']} – {preset_name}: {variant_name}",
                             build_action("variant", monitor["id"], preset_name, variant_name)))
    return rows


def show_shortcuts_dialog(root, eng, on_error):
    """Gyorsbillentyű-súgó (Linux): minden akció kész parancsa másolható, és a KDE Gyorsbillentyűk panel megnyitható.
    `on_error(szöveg)`: a panel megnyitásának hibaüzenete."""
    window = ctk.CTkToplevel(root)
    window.title("Gyorsbillentyűk (KDE)")
    window.geometry("760x520")
    ctk.CTkLabel(window, justify="left", anchor="w", wraplength=720,
                 text="Waylanden a program nem tud globális gyorsgombot figyelni, ezért a KDE köti a billentyűt a parancshoz: "
                      "Rendszerbeállítások → Gyorsbillentyűk → Új hozzáadása → Parancs vagy szkript. "
                      "Másold ki az alábbi parancsot, és rendelj hozzá billentyűkombinációt.").pack(
        fill="x", padx=16, pady=(14, 6))
    ctk.CTkButton(window, text="KDE Gyorsbillentyűk megnyitása",
                  command=lambda: open_shortcut_settings() or on_error("Nem található a systemsettings / kcmshell6.")).pack(
        anchor="w", padx=16, pady=(0, 8))
    row_list = ctk.CTkScrollableFrame(window)
    row_list.pack(fill="both", expand=True, padx=16, pady=(0, 14))
    for label, action in shortcut_rows(eng):
        if action is not None:
            _add_command_row(window, root, row_list, label, action_command(action))
    window.after(100, window.lift)


def _add_command_row(window, root, parent, label, command):
    """Egy sor: felirat, és alatta a parancs csak olvasható mezőben, „Másol" gombbal."""
    ctk.CTkLabel(parent, text=label, anchor="w", font=ctk.CTkFont(weight="bold")).pack(fill="x", pady=(8, 0))
    line = ctk.CTkFrame(parent, fg_color="transparent")
    line.pack(fill="x")
    command_entry = ctk.CTkEntry(line)
    command_entry.insert(0, command)
    command_entry.configure(state="readonly")
    command_entry.pack(side="left", fill="x", expand=True)
    copy_button = ctk.CTkButton(line, text="Másol", width=70)
    copy_button.configure(command=lambda: _copy_to_clipboard(window, root, command, copy_button))
    copy_button.pack(side="left", padx=(6, 0))


def _copy_to_clipboard(window, root, text, button):
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()
    button.configure(text="Másolva")
    window.after(COPIED_RESET_MS, lambda: button.winfo_exists() and button.configure(text="Másol"))
