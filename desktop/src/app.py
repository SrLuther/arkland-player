import re
import threading
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from typing import Optional

import customtkinter as ctk

from src.auth import start_steam_login
from src.api_client import ApiClient
from src.config_manager import ConfigManager

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

# ─── Paleta ───────────────────────────────────────────────────────────────
_BG_SIDEBAR  = "#161622"
_BG_MAIN     = "#1a1a2e"
_BG_CARD     = "#1e1e30"
_BG_INPUT    = "#12121e"
_GREEN       = "#00b09b"
_GREEN_HOVER = "#00937f"
_TEXT_DIM    = "#8888aa"
_TEXT        = "#e0e0f0"
_FONT        = ("Segoe UI", 12)
_FONT_SM     = ("Segoe UI", 10)
_FONT_TITLE  = ("Segoe UI", 20, "bold")
_FONT_SECTION= ("Segoe UI", 13, "bold")


def _extract_item_name(bp: str) -> str:
    """Converte um blueprint path ARK num nome legível."""
    try:
        last = bp.rsplit("/", 1)[-1].split(".")[0]
        for prefix in (
            "PrimalItemArmor_", "PrimalItemWeapon_", "PrimalItemResource_",
            "PrimalItemConsumable_", "PrimalItemStructure_",
            "PrimalItemSkin_", "PrimalItem_",
        ):
            if last.startswith(prefix):
                last = last[len(prefix):]
                break
        return re.sub(r"([A-Z])", r" \1", last).strip() or bp
    except Exception:
        return bp


class App:
    def __init__(self) -> None:
        self._cfg = ConfigManager()
        self._cfg.load()
        self._api: Optional[ApiClient] = None
        self._player_data: Optional[dict] = None

        self._root = ctk.CTk()
        self._root.title("ARKLAND Player")
        self._root.geometry("940x620")
        self._root.minsize(800, 540)
        self._root.configure(fg_color=_BG_MAIN)

        self._build_ui()

    # ─── Construção da UI ─────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._root.grid_rowconfigure(0, weight=1)
        self._root.grid_columnconfigure(0, weight=1)

        self._login_frame = self._build_login_frame()
        self._main_frame  = self._build_main_frame()

        self._login_frame.grid(row=0, column=0, sticky="nsew")
        self._main_frame.grid(row=0, column=0, sticky="nsew")

        if self._cfg.config.jwt_token:
            self._show_main()
        else:
            self._show_login()

    # ─── Frame de Login ───────────────────────────────────────────────────

    def _build_login_frame(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self._root, fg_color=_BG_MAIN)

        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(frame, fg_color=_BG_CARD, corner_radius=16, width=380)
        card.grid(row=0, column=0)
        card.grid_propagate(False)
        card.configure(width=380, height=460)

        ctk.CTkLabel(card, text="⬡", font=("Segoe UI", 52), text_color=_GREEN).place(relx=0.5, rely=0.15, anchor="center")
        ctk.CTkLabel(card, text="ARKLAND Player", font=_FONT_TITLE, text_color=_TEXT).place(relx=0.5, rely=0.30, anchor="center")
        ctk.CTkLabel(card, text="Inventário em Nuvem", font=_FONT_SM, text_color=_TEXT_DIM).place(relx=0.5, rely=0.38, anchor="center")

        ctk.CTkLabel(card, text="URL do Backend", font=_FONT_SM, text_color=_TEXT_DIM).place(relx=0.1, rely=0.48, anchor="w")
        self._url_entry = ctk.CTkEntry(
            card, width=300, height=36,
            fg_color=_BG_INPUT, border_color=_GREEN, corner_radius=8,
            font=_FONT, text_color=_TEXT,
        )
        self._url_entry.insert(0, self._cfg.config.backend_url)
        self._url_entry.place(relx=0.5, rely=0.56, anchor="center")

        self._login_btn = ctk.CTkButton(
            card, text="  Entrar com Steam", width=280, height=44,
            fg_color=_GREEN, hover_color=_GREEN_HOVER,
            font=("Segoe UI", 13, "bold"), corner_radius=10,
            command=self._on_steam_login,
        )
        self._login_btn.place(relx=0.5, rely=0.70, anchor="center")

        self._login_status = ctk.CTkLabel(card, text="", font=_FONT_SM, text_color=_TEXT_DIM)
        self._login_status.place(relx=0.5, rely=0.82, anchor="center")

        return frame

    # ─── Frame Principal ──────────────────────────────────────────────────

    def _build_main_frame(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self._root, fg_color=_BG_MAIN)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        # Sidebar
        sidebar = ctk.CTkFrame(frame, fg_color=_BG_SIDEBAR, width=180, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(8, weight=1)

        ctk.CTkLabel(sidebar, text="⬡", font=("Segoe UI", 32), text_color=_GREEN).grid(row=0, column=0, pady=(24, 0))
        ctk.CTkLabel(sidebar, text="ARKLAND\nPlayer", font=("Segoe UI", 11, "bold"), text_color=_TEXT, justify="center").grid(row=1, column=0, pady=(0, 24))

        self._nav_buttons: list[ctk.CTkButton] = []
        nav_items = [
            ("🏠  Dashboard",  self._show_dashboard),
            ("🎒  Inventário", self._show_inventory),
            ("📋  Histórico",  self._show_history),
            ("⚙️  Config",     self._show_settings),
        ]
        for i, (label, cmd) in enumerate(nav_items):
            btn = ctk.CTkButton(
                sidebar, text=label, width=160, height=40,
                fg_color="transparent", hover_color="#2a2a45",
                font=_FONT, text_color=_TEXT, anchor="w",
                corner_radius=8, command=cmd,
            )
            btn.grid(row=i + 2, column=0, padx=10, pady=3)
            self._nav_buttons.append(btn)

        self._logout_btn = ctk.CTkButton(
            sidebar, text="Sair", width=160, height=36,
            fg_color="#3a1a1a", hover_color="#5a2020",
            font=_FONT_SM, text_color="#ff6b6b", corner_radius=8,
            command=self._on_logout,
        )
        self._logout_btn.grid(row=9, column=0, padx=10, pady=(0, 20))

        # Content area
        content = ctk.CTkFrame(frame, fg_color=_BG_MAIN, corner_radius=0)
        content.grid(row=0, column=1, sticky="nsew")
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        self._dashboard_frame = self._build_dashboard(content)
        self._inventory_frame = self._build_inventory_frame(content)
        self._history_frame   = self._build_history_frame(content)
        self._settings_frame  = self._build_settings_frame(content)

        for f in (self._dashboard_frame, self._inventory_frame,
                  self._history_frame, self._settings_frame):
            f.grid(row=0, column=0, sticky="nsew")

        return frame

    # ─── Dashboard ────────────────────────────────────────────────────────

    def _build_dashboard(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=_BG_MAIN)

        ctk.CTkLabel(frame, text="Dashboard", font=_FONT_TITLE, text_color=_TEXT).pack(anchor="w", padx=24, pady=(24, 4))

        # Player card
        player_card = ctk.CTkFrame(frame, fg_color=_BG_CARD, corner_radius=12)
        player_card.pack(fill="x", padx=24, pady=8)

        self._dash_name_lbl  = ctk.CTkLabel(player_card, text="...", font=("Segoe UI", 15, "bold"), text_color=_TEXT)
        self._dash_name_lbl.grid(row=0, column=0, padx=16, pady=(12, 2), sticky="w")
        self._dash_sid_lbl   = ctk.CTkLabel(player_card, text="", font=_FONT_SM, text_color=_TEXT_DIM)
        self._dash_sid_lbl.grid(row=1, column=0, padx=16, pady=(0, 4), sticky="w")
        self._dash_group_lbl = ctk.CTkLabel(player_card, text="", font=_FONT_SM, text_color=_GREEN)
        self._dash_group_lbl.grid(row=2, column=0, padx=16, pady=(0, 12), sticky="w")

        # Stats row
        stats = ctk.CTkFrame(frame, fg_color="transparent")
        stats.pack(fill="x", padx=24, pady=4)
        for i in range(3):
            stats.grid_columnconfigure(i, weight=1)

        self._stat_snapshots = self._stat_card(stats, "Snapshots", "–", 0)
        self._stat_items     = self._stat_card(stats, "Itens (último)", "–", 1)
        self._stat_last_sync = self._stat_card(stats, "Último sync", "–", 2)

        # Hint
        ctk.CTkLabel(
            frame,
            text="Use /u no servidor ARK para salvar  •  /dow para restaurar",
            font=_FONT_SM, text_color=_TEXT_DIM,
        ).pack(pady=(12, 0))

        return frame

    def _stat_card(self, parent, title: str, value: str, col: int) -> ctk.CTkLabel:
        card = ctk.CTkFrame(parent, fg_color=_BG_CARD, corner_radius=12)
        card.grid(row=0, column=col, padx=6, pady=4, sticky="ew")
        ctk.CTkLabel(card, text=title, font=_FONT_SM, text_color=_TEXT_DIM).pack(pady=(10, 0))
        val_lbl = ctk.CTkLabel(card, text=value, font=("Segoe UI", 18, "bold"), text_color=_GREEN)
        val_lbl.pack(pady=(0, 10))
        return val_lbl

    # ─── Inventário ───────────────────────────────────────────────────────

    def _build_inventory_frame(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=_BG_MAIN)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(24, 4))

        ctk.CTkLabel(header, text="Inventário", font=_FONT_TITLE, text_color=_TEXT).pack(side="left")
        ctk.CTkButton(
            header, text="↻ Atualizar", width=100, height=32,
            fg_color=_BG_CARD, hover_color="#2a2a45",
            font=_FONT_SM, text_color=_TEXT, corner_radius=8,
            command=self._refresh_inventory,
        ).pack(side="right")

        self._inv_snapshot_lbl = ctk.CTkLabel(frame, text="", font=_FONT_SM, text_color=_TEXT_DIM)
        self._inv_snapshot_lbl.pack(anchor="w", padx=24, pady=(0, 8))

        # Treeview estilizado
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Ark.Treeview",
            background=_BG_CARD, foreground=_TEXT,
            fieldbackground=_BG_CARD, rowheight=26,
            borderwidth=0, font=("Segoe UI", 10),
        )
        style.configure("Ark.Treeview.Heading",
            background=_BG_SIDEBAR, foreground=_TEXT_DIM,
            font=("Segoe UI", 10, "bold"), relief="flat",
        )
        style.map("Ark.Treeview", background=[("selected", "#2a2a55")])

        cols = ("item", "qty", "quality", "durability", "equipado")
        self._inv_tree = ttk.Treeview(frame, columns=cols, show="headings", style="Ark.Treeview")
        self._inv_tree.heading("item",       text="Item")
        self._inv_tree.heading("qty",        text="Qtd")
        self._inv_tree.heading("quality",    text="Qualidade")
        self._inv_tree.heading("durability", text="Durabilidade")
        self._inv_tree.heading("equipado",   text="Equipado")
        self._inv_tree.column("item",       width=280, anchor="w")
        self._inv_tree.column("qty",        width=60,  anchor="center")
        self._inv_tree.column("quality",    width=100, anchor="center")
        self._inv_tree.column("durability", width=110, anchor="center")
        self._inv_tree.column("equipado",   width=80,  anchor="center")

        sb = ttk.Scrollbar(frame, orient="vertical", command=self._inv_tree.yview)
        self._inv_tree.configure(yscrollcommand=sb.set)

        self._inv_tree.pack(side="left", fill="both", expand=True, padx=(24, 0), pady=(0, 16))
        sb.pack(side="left", fill="y", pady=(0, 16))

        return frame

    # ─── Histórico ────────────────────────────────────────────────────────

    def _build_history_frame(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=_BG_MAIN)

        ctk.CTkLabel(frame, text="Histórico de Snapshots", font=_FONT_TITLE, text_color=_TEXT).pack(anchor="w", padx=24, pady=(24, 8))

        self._history_scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        self._history_scroll.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        return frame

    # ─── Configurações ────────────────────────────────────────────────────

    def _build_settings_frame(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=_BG_MAIN)

        ctk.CTkLabel(frame, text="Configurações", font=_FONT_TITLE, text_color=_TEXT).pack(anchor="w", padx=24, pady=(24, 16))

        card = ctk.CTkFrame(frame, fg_color=_BG_CARD, corner_radius=12)
        card.pack(fill="x", padx=24)

        ctk.CTkLabel(card, text="URL do Backend", font=_FONT_SM, text_color=_TEXT_DIM).pack(anchor="w", padx=16, pady=(14, 2))
        self._settings_url = ctk.CTkEntry(
            card, height=36, fg_color=_BG_INPUT, border_color=_GREEN,
            corner_radius=8, font=_FONT, text_color=_TEXT,
        )
        self._settings_url.pack(fill="x", padx=16, pady=(0, 14))

        ctk.CTkButton(
            card, text="Salvar", height=38,
            fg_color=_GREEN, hover_color=_GREEN_HOVER,
            font=("Segoe UI", 12, "bold"), corner_radius=8,
            command=self._save_settings,
        ).pack(fill="x", padx=16, pady=(0, 14))

        ctk.CTkButton(
            frame, text="Sair da conta", height=38,
            fg_color="#3a1a1a", hover_color="#5a2020",
            font=_FONT, text_color="#ff6b6b", corner_radius=8,
            command=self._on_logout,
        ).pack(fill="x", padx=24, pady=16)

        ctk.CTkLabel(frame, text="ARKLAND Player v1.0.0", font=_FONT_SM, text_color=_TEXT_DIM).pack(pady=4)

        return frame

    # ─── Navegação ────────────────────────────────────────────────────────

    def _nav_select(self, idx: int) -> None:
        for i, btn in enumerate(self._nav_buttons):
            btn.configure(fg_color=_GREEN if i == idx else "transparent")

    def _show_dashboard(self) -> None:
        self._nav_select(0)
        self._dashboard_frame.tkraise()
        threading.Thread(target=self._load_dashboard_data, daemon=True).start()

    def _show_inventory(self) -> None:
        self._nav_select(1)
        self._inventory_frame.tkraise()
        threading.Thread(target=self._refresh_inventory, daemon=True).start()

    def _show_history(self) -> None:
        self._nav_select(2)
        self._history_frame.tkraise()
        threading.Thread(target=self._load_history, daemon=True).start()

    def _show_settings(self) -> None:
        self._nav_select(3)
        self._settings_frame.tkraise()
        self._settings_url.delete(0, "end")
        self._settings_url.insert(0, self._cfg.config.backend_url)

    # ─── Visibilidade de telas ────────────────────────────────────────────

    def _show_login(self) -> None:
        self._main_frame.grid_remove()
        self._login_frame.tkraise()

    def _show_main(self) -> None:
        self._login_frame.grid_remove()
        cfg = self._cfg.config
        self._api = ApiClient(cfg.backend_url, cfg.jwt_token)
        self._main_frame.tkraise()
        self._show_dashboard()

    # ─── Ações ────────────────────────────────────────────────────────────

    def _on_steam_login(self) -> None:
        url = self._url_entry.get().strip()
        if not url:
            self._login_status.configure(text="Informe a URL do backend.", text_color="#ff6b6b")
            return

        self._cfg.config.backend_url = url
        self._login_status.configure(text="Aguardando login no navegador...", text_color=_TEXT_DIM)
        self._login_btn.configure(state="disabled")

        def _on_success(jwt: str, steam_id: str, persona_name: str) -> None:
            self._cfg.config.jwt_token    = jwt
            self._cfg.config.steam_id     = steam_id
            self._cfg.config.persona_name = persona_name
            self._cfg.save()
            self._root.after(0, self._show_main)

        def _on_error() -> None:
            self._login_btn.configure(state="normal")
            self._login_status.configure(text="Login cancelado ou expirado.", text_color="#ff6b6b")

        start_steam_login(url, _on_success)

        # Re-habilita o botão após 3 min
        self._root.after(180_000, lambda: self._login_btn.configure(state="normal"))

    def _on_logout(self) -> None:
        self._cfg.clear_session()
        self._api = None
        self._player_data = None
        self._show_login()

    def _save_settings(self) -> None:
        url = self._settings_url.get().strip()
        if url:
            self._cfg.config.backend_url = url
            self._cfg.save()
            if self._api:
                self._api.base_url = url

    # ─── Carregamento de dados ────────────────────────────────────────────

    def _load_dashboard_data(self) -> None:
        if not self._api:
            return
        player = self._api.get_me()
        snapshots = self._api.get_snapshots()

        def _update():
            if player:
                self._player_data = player
                self._dash_name_lbl.configure(text=player.get("persona_name", "—"))
                self._dash_sid_lbl.configure(text=f"SteamID: {player.get('steam_id', '')}")
                self._dash_group_lbl.configure(text=f"Grupo: {player.get('permission_group', '')}")
            if snapshots:
                last = snapshots[0]
                dt = self._fmt_date(last.get("uploaded_at", ""))
                self._stat_snapshots.configure(text=str(len(snapshots)))
                self._stat_items.configure(text=str(last.get("items_count", 0)))
                self._stat_last_sync.configure(text=dt)

        self._root.after(0, _update)

    def _refresh_inventory(self) -> None:
        if not self._api:
            return
        snapshots = self._api.get_snapshots()
        items = []
        snapshot_label = ""
        if snapshots:
            last = snapshots[0]
            items = self._api.get_snapshot_items(last["id"])
            dt = self._fmt_date(last.get("uploaded_at", ""))
            snapshot_label = f"Snapshot: {dt}  •  {last.get('server_name', '')}  [{last.get('map_name', '')}]"

        def _update():
            self._inv_snapshot_lbl.configure(text=snapshot_label)
            for row in self._inv_tree.get_children():
                self._inv_tree.delete(row)
            for item in items:
                name   = item.get("custom_name") or _extract_item_name(item.get("blueprint_path", ""))
                qty    = item.get("quantity", 1)
                qual   = f"{item.get('quality', 0.0) * 100:.0f}%"
                dur    = f"{item.get('durability', 0.0):.1f}"
                equip  = "✔" if item.get("is_equipped") else "–"
                self._inv_tree.insert("", "end", values=(name, qty, qual, dur, equip))

        self._root.after(0, _update)

    def _load_history(self) -> None:
        if not self._api:
            return
        snapshots = self._api.get_snapshots()

        def _update():
            for widget in self._history_scroll.winfo_children():
                widget.destroy()
            if not snapshots:
                ctk.CTkLabel(
                    self._history_scroll,
                    text="Nenhum snapshot encontrado.\nUse /u no servidor ARK para salvar seu inventário.",
                    font=_FONT, text_color=_TEXT_DIM, justify="center",
                ).pack(pady=40)
                return
            for s in snapshots:
                dt = self._fmt_date(s.get("uploaded_at", ""))
                card = ctk.CTkFrame(self._history_scroll, fg_color=_BG_CARD, corner_radius=10)
                card.pack(fill="x", pady=4)
                card.grid_columnconfigure(1, weight=1)

                ctk.CTkLabel(card, text=dt, font=("Segoe UI", 11, "bold"), text_color=_TEXT).grid(row=0, column=0, padx=14, pady=(8, 2), sticky="w")
                ctk.CTkLabel(card, text=f"{s.get('server_name', '–')}  •  {s.get('map_name', '–')}", font=_FONT_SM, text_color=_TEXT_DIM).grid(row=1, column=0, padx=14, pady=(0, 8), sticky="w")
                ctk.CTkLabel(card, text=f"{s.get('items_count', 0)} itens", font=_FONT_SM, text_color=_GREEN).grid(row=0, column=2, padx=14, rowspan=2, sticky="e")

        self._root.after(0, _update)

    # ─── Utilitários ──────────────────────────────────────────────────────

    @staticmethod
    def _fmt_date(iso: str) -> str:
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return iso

    def run(self) -> None:
        self._root.mainloop()
