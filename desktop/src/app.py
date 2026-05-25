import re
import sys
import pathlib
import threading
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from typing import Optional


def _app_root() -> pathlib.Path:
    """Raiz do app — funciona em modo dev e frozen (PyInstaller)."""
    if getattr(sys, "frozen", False):
        # sys._MEIPASS é a API oficial do PyInstaller para localizar dados
        # bundled (onedir: igual ao dir do exe; onefile: pasta temp extraida)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return pathlib.Path(meipass)
        return pathlib.Path(sys.executable).parent
    return pathlib.Path(__file__).parent.parent.parent


try:
    _VERSION = (_app_root() / "VERSION").read_text(encoding="utf-8").strip()
except (FileNotFoundError, OSError):
    _VERSION = "1.0.0"
_LOGO_PATH = _app_root() / "img" / "logo_akl_player.png"

import customtkinter as ctk

from src.auth import start_steam_login
from src.api_client import ApiClient
from src.config_manager import ConfigManager
from src.breed_store import BreedStore, Dino, STAT_KEYS, STAT_LABELS, STAT_DEFAULTS
from src.updater import UpdateChecker
from src.server_manager import ServerManager

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
        self._breed = BreedStore()
        self._breed.load()

        self._root = ctk.CTk()
        self._root.title("ARKLAND Player")
        self._root.geometry("940x620")
        self._root.minsize(800, 540)
        self._root.configure(fg_color=_BG_MAIN)

        # Carrega logo PNG (Pillow já está nas dependências)
        try:
            from PIL import Image as _PILImage
            _img = _PILImage.open(_LOGO_PATH)
            self._logo_lg = ctk.CTkImage(light_image=_img, dark_image=_img, size=(130, 130))
            self._logo_sm = ctk.CTkImage(light_image=_img, dark_image=_img, size=(54, 54))
        except Exception:
            self._logo_lg = None
            self._logo_sm = None

        self._nav_buttons: list[ctk.CTkButton] = []
        self._nav_idx: dict[str, int] = {}
        self._current_role = "player"
        self._update_checker = UpdateChecker(on_log=lambda m: None)
        self._update_info = None  # UpdateInfo quando disponível
        self._srv_mgr = ServerManager()
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
            self._show_main(self._cfg.config.role)
        else:
            self._show_login()

        # Verifica updates 5s após início
        self._root.after(5000, self._check_updates_on_start)

    # ─── Frame de Login ───────────────────────────────────────────────────

    def _build_login_frame(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self._root, fg_color=_BG_MAIN)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # Banner de update (place no topo, hidden por padrão)
        self._login_update_banner = ctk.CTkFrame(frame, fg_color="#1a3a2a", corner_radius=0, height=36)
        self._login_update_lbl = ctk.CTkLabel(
            self._login_update_banner, text="", font=_FONT_SM,
            text_color=_GREEN, cursor="hand2",
        )
        self._login_update_lbl.pack(expand=True)
        self._login_update_lbl.bind("<Button-1>", lambda e: self._do_update())

        card = ctk.CTkFrame(frame, fg_color=_BG_CARD, corner_radius=16)
        card.grid(row=0, column=0)
        card.grid_propagate(False)
        card.configure(width=380, height=580)

        # Logo
        if self._logo_lg:
            ctk.CTkLabel(card, image=self._logo_lg, text="").place(relx=0.5, rely=0.12, anchor="center")
        else:
            ctk.CTkLabel(card, text="⬡", font=("Segoe UI", 52), text_color=_GREEN).place(relx=0.5, rely=0.12, anchor="center")
        ctk.CTkLabel(card, text="ARKLAND Player", font=_FONT_TITLE, text_color=_TEXT).place(relx=0.5, rely=0.30, anchor="center")
        ctk.CTkLabel(card, text="Inventário em Nuvem", font=_FONT_SM, text_color=_TEXT_DIM).place(relx=0.5, rely=0.38, anchor="center")

        # ── Painel Steam (padrão) ──
        self._steam_panel = ctk.CTkFrame(card, fg_color="transparent", width=320, height=110)
        self._steam_panel.place(relx=0.5, rely=0.48, anchor="n")
        self._steam_panel.grid_propagate(False)

        self._login_btn = ctk.CTkButton(
            self._steam_panel, text="  Entrar com Steam", width=300, height=44,
            fg_color=_GREEN, hover_color=_GREEN_HOVER,
            font=("Segoe UI", 13, "bold"), corner_radius=10,
            command=self._on_steam_login,
        )
        self._login_btn.place(x=10, y=0)

        ctk.CTkButton(
            self._steam_panel, text="⚒ Ferramentas Locais", width=300, height=36,
            fg_color="transparent", hover_color="#2a2a45", border_width=1, border_color=_GREEN,
            font=_FONT_SM, text_color=_GREEN, corner_radius=10,
            command=lambda: self._show_main(),
        ).place(x=10, y=54)

        # ── Painel Dev (oculto por padrão) ──
        self._dev_panel = ctk.CTkFrame(card, fg_color="transparent", width=320, height=272)
        self._dev_panel.grid_propagate(False)

        ctk.CTkLabel(self._dev_panel, text="Servidor", font=_FONT_SM, text_color=_TEXT_DIM).place(x=10, y=0)
        self._dev_url_entry = ctk.CTkEntry(
            self._dev_panel, width=300, height=34,
            fg_color=_BG_INPUT, border_color="#444466", corner_radius=8,
            font=_FONT_SM, text_color=_TEXT,
        )
        self._dev_url_entry.insert(0, self._cfg.config.backend_url)
        self._dev_url_entry.place(x=10, y=18)

        ctk.CTkLabel(self._dev_panel, text="Usuário Dev", font=_FONT_SM, text_color=_TEXT_DIM).place(x=10, y=62)
        self._dev_user_entry = ctk.CTkEntry(
            self._dev_panel, width=300, height=34,
            fg_color=_BG_INPUT, border_color="#444466", corner_radius=8,
            font=_FONT, text_color=_TEXT,
        )
        self._dev_user_entry.place(x=10, y=80)

        ctk.CTkLabel(self._dev_panel, text="Senha", font=_FONT_SM, text_color=_TEXT_DIM).place(x=10, y=124)
        self._dev_pass_entry = ctk.CTkEntry(
            self._dev_panel, width=300, height=34,
            fg_color=_BG_INPUT, border_color="#444466", corner_radius=8,
            font=_FONT, text_color=_TEXT, show="●",
        )
        self._dev_pass_entry.place(x=10, y=142)

        self._dev_login_btn = ctk.CTkButton(
            self._dev_panel, text="Entrar como Dev", width=300, height=42,
            fg_color="#cc4444", hover_color="#aa2222",
            font=("Segoe UI", 12, "bold"), corner_radius=10,
            command=self._on_dev_login,
        )
        self._dev_login_btn.place(x=10, y=186)

        self._dev_login_status = ctk.CTkLabel(
            self._dev_panel, text="", font=_FONT_SM, text_color=_TEXT_DIM,
            wraplength=290,
        )
        self._dev_login_status.place(relx=0.5, y=237, anchor="n")

        # Status (painel steam)
        self._login_status = ctk.CTkLabel(card, text="", font=_FONT_SM, text_color=_TEXT_DIM)
        self._login_status.place(relx=0.5, rely=0.84, anchor="center")

        # Link sutil de acesso dev (quase invisível)
        _dev_link = ctk.CTkLabel(
            card, text="· acesso dev ·",
            font=("Segoe UI", 9), text_color="#333350",
            cursor="hand2",
        )
        _dev_link.place(relx=0.5, rely=0.93, anchor="center")
        _dev_link.bind("<Button-1>", lambda e: self._toggle_dev_panel())
        _dev_link.bind("<Enter>",    lambda e: _dev_link.configure(text_color="#666688"))
        _dev_link.bind("<Leave>",    lambda e: _dev_link.configure(text_color="#333350"))

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
        sidebar.grid_rowconfigure(20, weight=1)

        if self._logo_sm:
            ctk.CTkLabel(sidebar, image=self._logo_sm, text="").grid(row=0, column=0, pady=(16, 0))
        else:
            ctk.CTkLabel(sidebar, text="⬡", font=("Segoe UI", 32), text_color=_GREEN).grid(row=0, column=0, pady=(24, 0))
        ctk.CTkLabel(sidebar, text="ARKLAND\nPlayer", font=("Segoe UI", 11, "bold"), text_color=_TEXT, justify="center").grid(row=1, column=0, pady=(4, 20))

        # Nav buttons são adicionados dinamicamente por _setup_nav()
        self._logout_btn = ctk.CTkButton(
            sidebar, text="Sair", width=160, height=36,
            fg_color="#3a1a1a", hover_color="#5a2020",
            font=_FONT_SM, text_color="#ff6b6b", corner_radius=8,
            command=self._on_logout,
        )
        self._logout_btn.grid(row=21, column=0, padx=10, pady=(0, 4))

        # Label de notificação de update (oculto por padrão)
        self._sidebar_update_lbl = ctk.CTkLabel(
            sidebar, text="", font=("Segoe UI", 9), text_color="#ffaa44",
            cursor="hand2",
        )
        self._sidebar_update_lbl.grid(row=22, column=0, padx=10, pady=(0, 16))
        self._sidebar_update_lbl.bind("<Button-1>", lambda e: self._do_update())
        self._sidebar = sidebar

        # Content area
        content = ctk.CTkFrame(frame, fg_color=_BG_MAIN, corner_radius=0)
        content.grid(row=0, column=1, sticky="nsew")
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        self._dashboard_frame = self._build_dashboard(content)
        self._inventory_frame = self._build_inventory_frame(content)
        self._history_frame   = self._build_history_frame(content)
        self._breed_frame     = self._build_breed_frame(content)
        self._calc_frame      = self._build_calc_frame(content)
        self._settings_frame  = self._build_settings_frame(content)
        self._admin_frame     = self._build_admin_frame(content)
        self._dev_frame       = self._build_dev_frame(content)

        for f in (self._dashboard_frame, self._inventory_frame,
                  self._history_frame, self._breed_frame,
                  self._calc_frame, self._settings_frame,
                  self._admin_frame, self._dev_frame):
            f.grid(row=0, column=0, sticky="nsew")

        return frame

    # ─── Dashboard ────────────────────────────────────────────────────────

    def _build_dashboard(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=_BG_MAIN)

        ctk.CTkLabel(frame, text="Dashboard", font=_FONT_TITLE, text_color=_TEXT).pack(anchor="w", padx=24, pady=(24, 4))

        # Banner de atualização disponível (oculto por padrão)
        self._update_banner = ctk.CTkFrame(frame, fg_color="#2a1f00", corner_radius=10)
        self._update_banner_lbl = ctk.CTkLabel(
            self._update_banner,
            text="", font=("Segoe UI", 11), text_color="#ffcc55",
        )
        self._update_banner_lbl.pack(side="left", padx=16, pady=10)
        self._update_banner_btn = ctk.CTkButton(
            self._update_banner,
            text="Atualizar agora", width=130, height=28,
            fg_color="#cc8800", hover_color="#aa6600",
            font=_FONT_SM, text_color="#000", corner_radius=8,
            command=self._do_update,
        )
        self._update_banner_btn.pack(side="right", padx=16, pady=10)

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

    # ─── Breeding ─────────────────────────────────────────────────────────

    def _build_breed_frame(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=_BG_MAIN)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # Header
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 8))
        ctk.CTkLabel(header, text="Breeding Manager", font=_FONT_TITLE, text_color=_TEXT).pack(side="left")
        ctk.CTkButton(
            header, text="+ Adicionar Dino", width=130, height=32,
            fg_color=_GREEN, hover_color=_GREEN_HOVER,
            font=_FONT_SM, text_color="#000", corner_radius=8,
            command=self._open_add_dino_dialog,
        ).pack(side="right")

        # Body: two columns
        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 16))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        # Left: dino list
        self._breed_list_scroll = ctk.CTkScrollableFrame(body, fg_color=_BG_CARD, corner_radius=12, label_text="Meus Dinos", label_font=_FONT_SM, label_text_color=_TEXT_DIM)
        self._breed_list_scroll.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        # Right: simulator
        sim = ctk.CTkFrame(body, fg_color=_BG_CARD, corner_radius=12)
        sim.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        sim.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(sim, text="Simulador de Breeding", font=_FONT_SECTION, text_color=_TEXT).grid(row=0, column=0, columnspan=2, padx=16, pady=(16, 8), sticky="w")

        ctk.CTkLabel(sim, text="Macho", font=_FONT_SM, text_color=_TEXT_DIM).grid(row=1, column=0, padx=16, pady=(4, 0), sticky="w")
        self._breed_male_cb = ctk.CTkComboBox(sim, values=["—"], fg_color=_BG_INPUT, border_color=_GREEN, font=_FONT, text_color=_TEXT, state="readonly")
        self._breed_male_cb.grid(row=2, column=0, padx=16, pady=(0, 8), sticky="ew")

        ctk.CTkLabel(sim, text="Fêmea", font=_FONT_SM, text_color=_TEXT_DIM).grid(row=3, column=0, padx=16, pady=(4, 0), sticky="w")
        self._breed_female_cb = ctk.CTkComboBox(sim, values=["—"], fg_color=_BG_INPUT, border_color=_GREEN, font=_FONT, text_color=_TEXT, state="readonly")
        self._breed_female_cb.grid(row=4, column=0, padx=16, pady=(0, 12), sticky="ew")

        ctk.CTkButton(
            sim, text="⚡ Simular Breed", height=36,
            fg_color=_GREEN, hover_color=_GREEN_HOVER,
            font=("Segoe UI", 12, "bold"), text_color="#000", corner_radius=8,
            command=self._simulate_breed,
        ).grid(row=5, column=0, padx=16, pady=(0, 12), sticky="ew")

        # Offspring result area
        self._breed_result_frame = ctk.CTkFrame(sim, fg_color=_BG_INPUT, corner_radius=8)
        self._breed_result_frame.grid(row=6, column=0, padx=16, pady=(0, 16), sticky="nsew")
        sim.grid_rowconfigure(6, weight=1)
        ctk.CTkLabel(self._breed_result_frame, text="Selecione um casal para simular.", font=_FONT_SM, text_color=_TEXT_DIM).pack(padx=12, pady=16)

        return frame

    # ─── Calculadora ──────────────────────────────────────────────────────

    def _build_calc_frame(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=_BG_MAIN)
        frame.grid_rowconfigure(2, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text="Calculadora de Dinos", font=_FONT_TITLE, text_color=_TEXT).grid(row=0, column=0, padx=24, pady=(24, 4), sticky="w")

        # Multipliers row
        mults = ctk.CTkFrame(frame, fg_color=_BG_CARD, corner_radius=12)
        mults.grid(row=1, column=0, padx=24, pady=(0, 12), sticky="ew")
        ctk.CTkLabel(mults, text="Mult. Wild (servidor):", font=_FONT_SM, text_color=_TEXT_DIM).grid(row=0, column=0, padx=16, pady=10, sticky="w")
        self._calc_wild_mult = ctk.CTkEntry(mults, width=70, height=30, fg_color=_BG_INPUT, border_color=_GREEN, corner_radius=6, font=_FONT, text_color=_TEXT)
        self._calc_wild_mult.insert(0, "1.0")
        self._calc_wild_mult.grid(row=0, column=1, padx=(0, 24), pady=10)
        self._calc_wild_mult.bind("<KeyRelease>", lambda e: self._recalc_stats())

        ctk.CTkLabel(mults, text="Mult. Dom (servidor):", font=_FONT_SM, text_color=_TEXT_DIM).grid(row=0, column=2, padx=16, pady=10, sticky="w")
        self._calc_dom_mult = ctk.CTkEntry(mults, width=70, height=30, fg_color=_BG_INPUT, border_color=_GREEN, corner_radius=6, font=_FONT, text_color=_TEXT)
        self._calc_dom_mult.insert(0, "1.0")
        self._calc_dom_mult.grid(row=0, column=3, padx=(0, 16), pady=10)
        self._calc_dom_mult.bind("<KeyRelease>", lambda e: self._recalc_stats())

        ctk.CTkButton(mults, text="Resetar", width=80, height=30,
            fg_color=_BG_SIDEBAR, hover_color="#2a2a45", font=_FONT_SM, text_color=_TEXT_DIM, corner_radius=6,
            command=self._reset_calc,
        ).grid(row=0, column=4, padx=16, pady=10)

        # Stats table
        table = ctk.CTkScrollableFrame(frame, fg_color=_BG_CARD, corner_radius=12)
        table.grid(row=2, column=0, padx=24, pady=(0, 16), sticky="nsew")
        table.grid_columnconfigure((0, 1, 2, 3, 4, 5, 6), weight=1)

        headers = ["Stat", "Base", "Pts Wild", "Inc Wild %", "Pts Dom", "Inc Dom %", "Total"]
        for col, h in enumerate(headers):
            ctk.CTkLabel(table, text=h, font=("Segoe UI", 10, "bold"), text_color=_TEXT_DIM).grid(row=0, column=col, padx=8, pady=(10, 4))

        self._calc_entries: dict[str, dict] = {}
        for row_idx, key in enumerate(STAT_KEYS, start=1):
            label = STAT_LABELS[key]
            wild_inc_def, dom_inc_def = STAT_DEFAULTS[key]

            ctk.CTkLabel(table, text=label, font=("Segoe UI", 11, "bold"), text_color=_TEXT).grid(row=row_idx, column=0, padx=12, pady=4, sticky="w")

            def _make_entry(w=80):
                e = ctk.CTkEntry(table, width=w, height=28, fg_color=_BG_INPUT, border_color="#333355", corner_radius=6, font=_FONT_SM, text_color=_TEXT)
                e.bind("<KeyRelease>", lambda ev: self._recalc_stats())
                return e

            base_e = _make_entry(90)
            base_e.grid(row=row_idx, column=1, padx=4, pady=4)

            wild_pts_e = _make_entry()
            wild_pts_e.insert(0, "0")
            wild_pts_e.grid(row=row_idx, column=2, padx=4, pady=4)

            wild_inc_e = _make_entry()
            wild_inc_e.insert(0, f"{wild_inc_def:.2f}")
            wild_inc_e.grid(row=row_idx, column=3, padx=4, pady=4)

            dom_pts_e = _make_entry()
            dom_pts_e.insert(0, "0")
            dom_pts_e.grid(row=row_idx, column=4, padx=4, pady=4)

            dom_inc_e = _make_entry()
            dom_inc_e.insert(0, f"{dom_inc_def:.2f}")
            dom_inc_e.grid(row=row_idx, column=5, padx=4, pady=4)

            result_lbl = ctk.CTkLabel(table, text="—", font=("Segoe UI", 12, "bold"), text_color=_GREEN, width=90)
            result_lbl.grid(row=row_idx, column=6, padx=12, pady=4)

            self._calc_entries[key] = {
                "base": base_e, "wild_pts": wild_pts_e, "wild_inc": wild_inc_e,
                "dom_pts": dom_pts_e, "dom_inc": dom_inc_e, "result": result_lbl,
            }

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

        ctk.CTkLabel(frame, text=f"ARKLAND Player v{_VERSION}", font=_FONT_SM, text_color=_TEXT_DIM).pack(pady=4)

        return frame

    # ─── Painel Administração ─────────────────────────────────────────────

    def _build_admin_frame(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=_BG_MAIN)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(24, 4))
        ctk.CTkLabel(header, text="Jogadores", font=_FONT_TITLE, text_color=_TEXT).pack(side="left")
        ctk.CTkButton(
            header, text="↻ Atualizar", width=100, height=32,
            fg_color=_BG_CARD, hover_color="#2a2a45",
            font=_FONT_SM, text_color=_TEXT, corner_radius=8,
            command=lambda: threading.Thread(target=self._refresh_admin, daemon=True).start(),
        ).pack(side="right")

        cols = ("name", "steam_id", "group", "last_seen")
        self._admin_tree = ttk.Treeview(frame, columns=cols, show="headings", style="Ark.Treeview")
        self._admin_tree.heading("name",      text="Nome")
        self._admin_tree.heading("steam_id",  text="SteamID")
        self._admin_tree.heading("group",     text="Grupo")
        self._admin_tree.heading("last_seen", text="Último acesso")
        self._admin_tree.column("name",      width=200, anchor="w")
        self._admin_tree.column("steam_id",  width=160, anchor="center")
        self._admin_tree.column("group",     width=110, anchor="center")
        self._admin_tree.column("last_seen", width=160, anchor="center")

        sb = ttk.Scrollbar(frame, orient="vertical", command=self._admin_tree.yview)
        self._admin_tree.configure(yscrollcommand=sb.set)
        self._admin_tree.pack(side="left", fill="both", expand=True, padx=(24, 0), pady=(0, 16))
        sb.pack(side="left", fill="y", pady=(0, 16))

        return frame

    # ─── Painel Dev ───────────────────────────────────────────────────────

    def _build_dev_frame(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=_BG_MAIN)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text="Sistema Dev", font=_FONT_TITLE, text_color=_TEXT).grid(
            row=0, column=0, padx=24, pady=(24, 8), sticky="w",
        )

        tabs = ctk.CTkTabview(
            frame,
            fg_color=_BG_CARD,
            segmented_button_fg_color=_BG_SIDEBAR,
            segmented_button_selected_color=_GREEN,
            segmented_button_selected_hover_color=_GREEN_HOVER,
            segmented_button_unselected_color=_BG_SIDEBAR,
            segmented_button_unselected_hover_color="#2a2a45",
            text_color=_TEXT,
            corner_radius=12,
        )
        tabs.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 16))

        for name in ("Status", "Usuários Dev", "Permissões ARK", "Banco de Dados", "Logs", "Configurações", "Bot Discord"):
            tabs.add(name)

        self._build_dev_tab_status(tabs.tab("Status"))
        self._build_dev_tab_users(tabs.tab("Usuários Dev"))
        self._build_dev_tab_permissions(tabs.tab("Permissões ARK"))
        self._build_dev_tab_database(tabs.tab("Banco de Dados"))
        self._build_dev_tab_logs(tabs.tab("Logs"))
        self._build_dev_tab_config(tabs.tab("Configurações"))
        self._build_dev_tab_bot(tabs.tab("Bot Discord"))

        return frame

    def _build_dev_tab_status(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure((0, 1), weight=1)
        tab.grid_rowconfigure((0, 1), weight=1)

        def _health_card(r: int, c: int, title: str, attr: str) -> None:
            card = ctk.CTkFrame(tab, fg_color=_BG_MAIN, corner_radius=10)
            card.grid(row=r, column=c, padx=8, pady=8, sticky="nsew")
            ctk.CTkLabel(card, text=title, font=_FONT_SM, text_color=_TEXT_DIM).pack(pady=(14, 4))
            lbl = ctk.CTkLabel(card, text="—", font=("Segoe UI", 15, "bold"), text_color=_TEXT_DIM)
            lbl.pack(pady=(0, 14))
            setattr(self, attr, lbl)

        _health_card(0, 0, "Backend",       "_health_backend_lbl")
        _health_card(0, 1, "Banco de Dados", "_health_db_lbl")
        _health_card(1, 0, "Steam API",      "_health_steam_lbl")
        _health_card(1, 1, "Uptime",         "_health_uptime_lbl")

        ctk.CTkButton(
            tab, text="↻ Verificar Status", height=34, width=160,
            fg_color=_BG_SIDEBAR, hover_color="#2a2a45",
            font=_FONT_SM, text_color=_TEXT, corner_radius=8,
            command=lambda: threading.Thread(target=self._refresh_health, daemon=True).start(),
        ).grid(row=2, column=0, columnspan=2, pady=(0, 12))

    def _build_dev_tab_users(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        form = ctk.CTkFrame(tab, fg_color=_BG_MAIN, corner_radius=10)
        form.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        form.grid_columnconfigure(1, weight=1)
        form.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(form, text="Novo:", font=_FONT_SM, text_color=_TEXT_DIM).grid(
            row=0, column=0, padx=(12, 6), pady=10, sticky="w",
        )
        self._new_dev_user = ctk.CTkEntry(
            form, height=34, fg_color=_BG_INPUT, border_color=_GREEN,
            corner_radius=8, font=_FONT, text_color=_TEXT, placeholder_text="usuário",
        )
        self._new_dev_user.grid(row=0, column=1, padx=(0, 6), pady=10, sticky="ew")
        self._new_dev_pass = ctk.CTkEntry(
            form, height=34, fg_color=_BG_INPUT, border_color=_GREEN,
            corner_radius=8, font=_FONT, text_color=_TEXT, show="●", placeholder_text="senha",
        )
        self._new_dev_pass.grid(row=0, column=2, padx=(0, 6), pady=10, sticky="ew")
        ctk.CTkButton(
            form, text="Criar", width=70, height=34,
            fg_color=_GREEN, hover_color=_GREEN_HOVER,
            font=_FONT_SM, text_color="#000", corner_radius=8,
            command=self._create_dev_user,
        ).grid(row=0, column=3, padx=(0, 12), pady=10)

        self._dev_frame_status = ctk.CTkLabel(form, text="", font=_FONT_SM, text_color=_TEXT_DIM)
        self._dev_frame_status.grid(row=1, column=0, columnspan=4, padx=12, pady=(0, 6))

        self._dev_users_scroll = ctk.CTkScrollableFrame(
            tab, fg_color="transparent",
            label_text="Usuários cadastrados", label_font=_FONT_SM, label_text_color=_TEXT_DIM,
        )
        self._dev_users_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))
        self._dev_users_scroll.grid_columnconfigure(0, weight=1)

    def _build_dev_tab_permissions(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            tab, text="Grupos ARK que recebem role de admin:",
            font=_FONT_SM, text_color=_TEXT_DIM,
        ).pack(anchor="w", padx=12, pady=(14, 2))
        ctk.CTkLabel(
            tab, text="Separe com vírgulas  •  Ex: admin, mod, owner, Staff",
            font=("Segoe UI", 9), text_color=_TEXT_DIM,
        ).pack(anchor="w", padx=12)
        self._perm_admin_groups_entry = ctk.CTkEntry(
            tab, height=36, fg_color=_BG_INPUT, border_color=_GREEN,
            corner_radius=8, font=_FONT, text_color=_TEXT,
        )
        self._perm_admin_groups_entry.pack(fill="x", padx=12, pady=(4, 8))
        ctk.CTkButton(
            tab, text="Salvar Permissões", height=36,
            fg_color=_GREEN, hover_color=_GREEN_HOVER,
            font=("Segoe UI", 12, "bold"), corner_radius=8,
            command=self._save_permissions,
        ).pack(fill="x", padx=12, pady=(0, 8))
        self._perm_status_lbl = ctk.CTkLabel(tab, text="", font=_FONT_SM, text_color=_TEXT_DIM)
        self._perm_status_lbl.pack(pady=4)
        ctk.CTkLabel(
            tab, text="⚠  Alterações afetam apenas novos logins Steam",
            font=_FONT_SM, text_color="#cc8833",
        ).pack(pady=(8, 0))

    def _build_dev_tab_database(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)
        for i, (attr, title) in enumerate([
            ("_dev_stat_players",   "Jogadores"),
            ("_dev_stat_snapshots", "Snapshots"),
            ("_dev_stat_items",     "Itens Total"),
            ("_dev_stat_devusers",  "Devs"),
            ("_dev_stat_logs",      "Logs"),
        ]):
            card = ctk.CTkFrame(tab, fg_color=_BG_MAIN, corner_radius=10)
            card.grid(row=0, column=i, padx=4, pady=8, sticky="ew")
            ctk.CTkLabel(card, text=title, font=_FONT_SM, text_color=_TEXT_DIM).pack(pady=(8, 0))
            lbl = ctk.CTkLabel(card, text="–", font=("Segoe UI", 18, "bold"), text_color=_GREEN)
            lbl.pack(pady=(0, 8))
            setattr(self, attr, lbl)

        cleanup = ctk.CTkFrame(tab, fg_color=_BG_MAIN, corner_radius=10)
        cleanup.grid(row=1, column=0, columnspan=5, padx=8, pady=(4, 4), sticky="ew")
        cleanup.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(cleanup, text="Limpar snapshots mais antigos que", font=_FONT_SM, text_color=_TEXT_DIM).grid(
            row=0, column=0, padx=12, pady=12, sticky="w",
        )
        self._cleanup_days_entry = ctk.CTkEntry(
            cleanup, width=60, height=34,
            fg_color=_BG_INPUT, border_color=_GREEN, corner_radius=8,
            font=_FONT, text_color=_TEXT,
        )
        self._cleanup_days_entry.insert(0, "30")
        self._cleanup_days_entry.grid(row=0, column=1, padx=8, pady=12, sticky="w")
        ctk.CTkLabel(cleanup, text="dias", font=_FONT_SM, text_color=_TEXT_DIM).grid(
            row=0, column=2, padx=(0, 8), pady=12, sticky="w",
        )
        ctk.CTkButton(
            cleanup, text="Limpar", width=100, height=34,
            fg_color="#cc4444", hover_color="#aa2222",
            font=_FONT_SM, text_color=_TEXT, corner_radius=8,
            command=self._cleanup_database,
        ).grid(row=0, column=3, padx=12, pady=12)
        self._db_cleanup_status = ctk.CTkLabel(tab, text="", font=_FONT_SM, text_color=_TEXT_DIM)
        self._db_cleanup_status.grid(row=2, column=0, columnspan=5, pady=4)

    def _build_dev_tab_logs(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(tab, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 4))
        ctk.CTkLabel(header, text="Últimos 100 eventos", font=_FONT_SM, text_color=_TEXT_DIM).pack(side="left")
        ctk.CTkButton(
            header, text="↻ Atualizar", width=100, height=28,
            fg_color=_BG_SIDEBAR, hover_color="#2a2a45",
            font=_FONT_SM, text_color=_TEXT, corner_radius=8,
            command=lambda: threading.Thread(target=self._refresh_audit_logs, daemon=True).start(),
        ).pack(side="right")
        cols = ("timestamp", "event", "identifier", "role", "ip")
        self._audit_tree = ttk.Treeview(tab, columns=cols, show="headings", style="Ark.Treeview", height=12)
        self._audit_tree.heading("timestamp",  text="Data/Hora")
        self._audit_tree.heading("event",      text="Evento")
        self._audit_tree.heading("identifier", text="Usuário/SteamID")
        self._audit_tree.heading("role",       text="Role")
        self._audit_tree.heading("ip",         text="IP")
        self._audit_tree.column("timestamp",  width=140, anchor="center")
        self._audit_tree.column("event",      width=140, anchor="center")
        self._audit_tree.column("identifier", width=160, anchor="w")
        self._audit_tree.column("role",       width=80,  anchor="center")
        self._audit_tree.column("ip",         width=120, anchor="center")
        sb = ttk.Scrollbar(tab, orient="vertical", command=self._audit_tree.yview)
        self._audit_tree.configure(yscrollcommand=sb.set)
        self._audit_tree.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=(0, 8))
        sb.grid(row=1, column=1, sticky="ns", pady=(0, 8))
        tab.grid_columnconfigure(1, weight=0)

    def _build_dev_tab_config(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)
        _fields = [
            ("cors_origins",       "CORS Origins",        '["http://localhost"]'),
            ("steam_return_url",   "Steam Return URL",    "http://localhost:5000/auth/steam/callback"),
            ("jwt_expire_minutes", "JWT Expiração (min)", "1440"),
            ("admin_groups",       "Grupos Admin (JSON)", '["admin", "mod", "owner"]'),
        ]
        self._cfg_entries: dict[str, ctk.CTkEntry] = {}
        for key, label, placeholder in _fields:
            ctk.CTkLabel(tab, text=label, font=_FONT_SM, text_color=_TEXT_DIM).pack(
                anchor="w", padx=12, pady=(10, 2),
            )
            entry = ctk.CTkEntry(
                tab, height=34, fg_color=_BG_INPUT, border_color=_GREEN,
                corner_radius=8, font=_FONT_SM, text_color=_TEXT,
                placeholder_text=placeholder,
            )
            entry.pack(fill="x", padx=12, pady=(0, 2))
            self._cfg_entries[key] = entry
        ctk.CTkButton(
            tab, text="Salvar Configurações", height=36,
            fg_color=_GREEN, hover_color=_GREEN_HOVER,
            font=("Segoe UI", 12, "bold"), corner_radius=8,
            command=self._save_backend_config,
        ).pack(fill="x", padx=12, pady=(10, 4))
        self._config_status_lbl = ctk.CTkLabel(tab, text="", font=_FONT_SM, text_color=_TEXT_DIM)
        self._config_status_lbl.pack(pady=4)

    def _build_dev_tab_bot(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(2, weight=1)

        # ── Status + controles ──────────────────────────────────────────────
        status_row = ctk.CTkFrame(tab, fg_color=_BG_MAIN, corner_radius=10)
        status_row.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        status_row.grid_columnconfigure(1, weight=1)

        self._bot_status_lbl = ctk.CTkLabel(
            status_row, text="● Desconhecido", font=("Segoe UI", 13, "bold"), text_color=_TEXT_DIM,
        )
        self._bot_status_lbl.grid(row=0, column=0, padx=12, pady=(10, 2), sticky="w")
        self._bot_uptime_lbl = ctk.CTkLabel(status_row, text="", font=_FONT_SM, text_color=_TEXT_DIM)
        self._bot_uptime_lbl.grid(row=0, column=1, padx=8, pady=(10, 2), sticky="w")

        # Máquina / caminho — confirma qual instância está sendo gerenciada
        self._bot_machine_lbl = ctk.CTkLabel(
            status_row, text="", font=("Segoe UI", 9), text_color="#555577",
        )
        self._bot_machine_lbl.grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 8), sticky="w")

        btn_frame = ctk.CTkFrame(status_row, fg_color="transparent")
        btn_frame.grid(row=0, column=2, rowspan=2, padx=12, pady=6)
        for text, color, hover, cmd in [
            ("▶ Start",   _GREEN,    _GREEN_HOVER, self._bot_start),
            ("■ Stop",    "#cc4444", "#aa2222",    self._bot_stop),
            ("↺ Restart", "#4466cc", "#3355aa",    self._bot_restart),
        ]:
            ctk.CTkButton(
                btn_frame, text=text, width=85, height=30,
                fg_color=color, hover_color=hover,
                font=_FONT_SM, text_color=_TEXT if text != "▶ Start" else "#000",
                corner_radius=8,
                command=cmd,
            ).pack(side="left", padx=3)

        # ── Cogs ────────────────────────────────────────────────────────────
        cogs_outer = ctk.CTkFrame(tab, fg_color=_BG_MAIN, corner_radius=10)
        cogs_outer.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 4))
        cogs_outer.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(cogs_outer, text="Cogs", font=_FONT_SM, text_color=_TEXT_DIM).pack(
            anchor="w", padx=12, pady=(8, 4),
        )
        self._cogs_frame = ctk.CTkScrollableFrame(cogs_outer, fg_color="transparent", height=80)
        self._cogs_frame.pack(fill="x", padx=8, pady=(0, 8))
        self._cogs_frame.grid_columnconfigure(tuple(range(6)), weight=1)

        # ── Logs ────────────────────────────────────────────────────────────
        log_outer = ctk.CTkFrame(tab, fg_color=_BG_MAIN, corner_radius=10)
        log_outer.grid(row=2, column=0, sticky="nsew", padx=8, pady=(4, 4))
        log_outer.grid_rowconfigure(1, weight=1)
        log_outer.grid_columnconfigure(0, weight=1)

        log_header = ctk.CTkFrame(log_outer, fg_color="transparent")
        log_header.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        ctk.CTkLabel(log_header, text="Logs do Bot", font=_FONT_SM, text_color=_TEXT_DIM).pack(side="left")
        for text, cmd in [("↻ Atualizar", self._refresh_bot_logs), ("🗑 Limpar", self._clear_bot_logs)]:
            ctk.CTkButton(
                log_header, text=text, width=90, height=26,
                fg_color=_BG_SIDEBAR, hover_color="#2a2a45",
                font=_FONT_SM, text_color=_TEXT, corner_radius=8,
                command=cmd,
            ).pack(side="right", padx=3)

        self._bot_log_text = ctk.CTkTextbox(
            log_outer, fg_color=_BG_INPUT, text_color=_TEXT,
            font=("Consolas", 10), corner_radius=8, wrap="none",
        )
        self._bot_log_text.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        # ── Config ──────────────────────────────────────────────────────────
        cfg_outer = ctk.CTkFrame(tab, fg_color=_BG_MAIN, corner_radius=10)
        cfg_outer.grid(row=3, column=0, sticky="ew", padx=8, pady=(4, 8))
        cfg_outer.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(cfg_outer, text="Configurações do Bot (.env)", font=_FONT_SM, text_color=_TEXT_DIM).pack(
            anchor="w", padx=12, pady=(8, 4),
        )

        self._bot_cfg_scroll = ctk.CTkScrollableFrame(cfg_outer, fg_color="transparent", height=120)
        self._bot_cfg_scroll.pack(fill="x", padx=8)
        self._bot_cfg_scroll.grid_columnconfigure(1, weight=1)
        self._bot_cfg_entries: dict[str, ctk.CTkEntry] = {}

        btn_row = ctk.CTkFrame(cfg_outer, fg_color="transparent")
        btn_row.pack(fill="x", padx=8, pady=6)
        ctk.CTkButton(
            btn_row, text="Salvar .env", width=120, height=30,
            fg_color=_GREEN, hover_color=_GREEN_HOVER,
            font=_FONT_SM, text_color="#000", corner_radius=8,
            command=self._save_bot_config,
        ).pack(side="left")
        self._bot_cfg_status_lbl = ctk.CTkLabel(btn_row, text="", font=_FONT_SM, text_color=_TEXT_DIM)
        self._bot_cfg_status_lbl.pack(side="left", padx=10)

    # ─── Dev: Bot callbacks ───────────────────────────────────────────────────

    def _refresh_bot_status(self) -> None:
        if not self._api:
            return
        status = self._api.get_bot_status()

        def _update():
            # Mostra sempre qual máquina/instância está sendo gerenciada
            host = self._cfg.config.backend_url if self._cfg else ""
            bot_dir = status.get("bot_dir", "") if status else ""
            hostname = status.get("hostname", "") if status else ""
            machine_info = f"Servidor: {hostname}  |  {host}  |  {bot_dir}" if hostname else f"{host}  |  {bot_dir}"
            self._bot_machine_lbl.configure(
                text=machine_info if bot_dir else f"Backend: {host}"
            )

            if not status:
                self._bot_status_lbl.configure(text="● Inacessível", text_color="#ff6b6b")
                self._bot_uptime_lbl.configure(text="")
                return
            if status.get("running"):
                self._bot_status_lbl.configure(text="● Online", text_color=_GREEN)
                uptime = int(status.get("uptime_seconds") or 0)
                h, rem = divmod(uptime, 3600)
                m = rem // 60
                self._bot_uptime_lbl.configure(text=f"Uptime: {h}h {m:02d}m  |  PID {status.get('pid')}")
            else:
                self._bot_status_lbl.configure(text="● Parado", text_color=_TEXT_DIM)
                self._bot_uptime_lbl.configure(text="")
        self._root.after(0, _update)

    def _bot_start(self) -> None:
        def _do():
            result = self._api.bot_start() if self._api else None
            self._root.after(0, lambda: threading.Thread(target=self._refresh_bot_status, daemon=True).start())
        threading.Thread(target=_do, daemon=True).start()

    def _bot_stop(self) -> None:
        def _do():
            result = self._api.bot_stop() if self._api else None
            self._root.after(0, lambda: threading.Thread(target=self._refresh_bot_status, daemon=True).start())
        threading.Thread(target=_do, daemon=True).start()

    def _bot_restart(self) -> None:
        def _do():
            result = self._api.bot_restart() if self._api else None
            self._root.after(0, lambda: threading.Thread(target=self._refresh_bot_status, daemon=True).start())
        threading.Thread(target=_do, daemon=True).start()

    def _refresh_bot_logs(self) -> None:
        if not self._api:
            return
        lines = self._api.get_bot_logs(lines=200)

        def _update():
            self._bot_log_text.configure(state="normal")
            self._bot_log_text.delete("1.0", "end")
            self._bot_log_text.insert("end", "\n".join(lines))
            self._bot_log_text.see("end")
            self._bot_log_text.configure(state="disabled")
        self._root.after(0, _update)

    def _clear_bot_logs(self) -> None:
        def _do():
            if self._api:
                self._api.clear_bot_logs()
            self._root.after(0, lambda: threading.Thread(target=self._refresh_bot_logs, daemon=True).start())
        threading.Thread(target=_do, daemon=True).start()

    def _refresh_bot_cogs(self) -> None:
        if not self._api:
            return
        cogs = self._api.get_bot_cogs()

        def _update():
            for w in self._cogs_frame.winfo_children():
                w.destroy()
            for i, cog in enumerate(cogs):
                col = i % 6
                row = i // 6
                color = _GREEN if cog["enabled"] else "#444466"
                name = cog["name"]
                enabled = cog["enabled"]
                btn = ctk.CTkButton(
                    self._cogs_frame,
                    text=f"{'✔' if enabled else '✘'} {name}",
                    width=100, height=28,
                    fg_color=color if enabled else "#333355",
                    hover_color=_GREEN_HOVER if enabled else "#444477",
                    font=("Segoe UI", 10), text_color=_TEXT,
                    corner_radius=6,
                    command=lambda n=name, e=enabled: threading.Thread(
                        target=lambda: [
                            self._api.toggle_bot_cog(n, not e) if self._api else None,
                            self._root.after(0, lambda: threading.Thread(target=self._refresh_bot_cogs, daemon=True).start()),
                        ],
                        daemon=True,
                    ).start(),
                )
                btn.grid(row=row, column=col, padx=3, pady=3, sticky="ew")
        self._root.after(0, _update)

    def _load_bot_config(self) -> None:
        if not self._api:
            return
        config = self._api.get_bot_config()

        _IMPORTANT_KEYS = [
            "DISCORD_TOKEN", "ARK_HOST", "ARK_RCON_PASSWORD",
            "ARK_MAP1_NAME", "ARK_MAP1_PORT",
            "ARK_MAP2_NAME", "ARK_MAP2_PORT",
            "ARK_MAP3_NAME", "ARK_MAP3_PORT",
            "TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET",
            "STEAM_API_KEY",
        ]

        def _update():
            if not config:
                return
            for w in self._bot_cfg_scroll.winfo_children():
                w.destroy()
            self._bot_cfg_entries.clear()

            # Mostra chaves importantes primeiro, depois as restantes
            ordered = [k for k in _IMPORTANT_KEYS if k in config]
            ordered += [k for k in config if k not in _IMPORTANT_KEYS]

            for i, key in enumerate(ordered):
                ctk.CTkLabel(
                    self._bot_cfg_scroll, text=key, font=_FONT_SM, text_color=_TEXT_DIM, width=220, anchor="e",
                ).grid(row=i, column=0, padx=(4, 8), pady=2, sticky="e")
                show = "●" if "TOKEN" in key or "PASSWORD" in key or "SECRET" in key else ""
                entry = ctk.CTkEntry(
                    self._bot_cfg_scroll, height=28,
                    fg_color=_BG_INPUT, border_color=_GREEN,
                    corner_radius=6, font=_FONT_SM, text_color=_TEXT,
                    show=show,
                )
                entry.insert(0, config[key])
                entry.grid(row=i, column=1, padx=(0, 4), pady=2, sticky="ew")
                self._bot_cfg_entries[key] = entry
        self._root.after(0, _update)

    def _save_bot_config(self) -> None:
        changes = {k: e.get().strip() for k, e in self._bot_cfg_entries.items() if e.get().strip()}
        if not changes:
            return

        def _do():
            result = self._api.update_bot_config(changes) if self._api else None

            def _update():
                if result:
                    self._bot_cfg_status_lbl.configure(text="✔ Salvo. Reinicie o bot.", text_color=_GREEN)
                else:
                    self._bot_cfg_status_lbl.configure(text="Erro ao salvar.", text_color="#ff6b6b")
            self._root.after(0, _update)
        threading.Thread(target=_do, daemon=True).start()

    def _setup_nav(self, role: str) -> None:
        """Reconstrói os botões de navegação conforme o role do usuário."""
        for btn in self._nav_buttons:
            btn.grid_forget()
            btn.destroy()
        self._nav_buttons = []
        self._nav_idx = {}

        if role == "dev":
            nav_items = [
                ("dashboard", "🏠  Dashboard",    self._show_dashboard),
                ("admin",     "👥  Jogadores",    self._show_admin),
                ("dev",       "📊  Sistema",      self._show_dev),
                ("breed",     "🦕  Breeding",     self._show_breed),
                ("calc",      "🧮  Calculadora",  self._show_calc),
                ("settings",  "⚙️  Config",       self._show_settings),
            ]
        elif role == "admin":
            nav_items = [
                ("dashboard", "🏠  Dashboard",    self._show_dashboard),
                ("inventory", "🎒  Inventário",   self._show_inventory),
                ("history",   "📋  Histórico",    self._show_history),
                ("admin",     "👥  Jogadores",    self._show_admin),
                ("breed",     "🦕  Breeding",     self._show_breed),
                ("calc",      "🧮  Calculadora",  self._show_calc),
                ("settings",  "⚙️  Config",       self._show_settings),
            ]
        else:  # player
            nav_items = [
                ("dashboard", "🏠  Dashboard",    self._show_dashboard),
                ("inventory", "🎒  Inventário",   self._show_inventory),
                ("history",   "📋  Histórico",    self._show_history),
                ("breed",     "🦕  Breeding",     self._show_breed),
                ("calc",      "🧮  Calculadora",  self._show_calc),
                ("settings",  "⚙️  Config",       self._show_settings),
            ]

        for i, (key, label, cmd) in enumerate(nav_items):
            btn = ctk.CTkButton(
                self._sidebar, text=label, width=160, height=40,
                fg_color="transparent", hover_color="#2a2a45",
                font=_FONT, text_color=_TEXT, anchor="w",
                corner_radius=8, command=cmd,
            )
            btn.grid(row=i + 2, column=0, padx=10, pady=3)
            self._nav_buttons.append(btn)
            self._nav_idx[key] = i

        self._current_role = role

    def _toggle_dev_panel(self) -> None:
        """Alterna a visibilidade do painel Dev no card de login."""
        if self._dev_panel.winfo_ismapped():
            self._dev_login_status.configure(text="")
            self._dev_panel.place_forget()
            self._steam_panel.place(relx=0.5, rely=0.48, anchor="n")
            self._login_status.place(relx=0.5, rely=0.84, anchor="center")
        else:
            self._login_status.configure(text="")
            self._login_status.place_forget()
            self._steam_panel.place_forget()
            self._dev_panel.place(relx=0.5, rely=0.44, anchor="n")



    # ─── Navegação ────────────────────────────────────────────────────────

    def _nav_select(self, idx: int) -> None:
        for i, btn in enumerate(self._nav_buttons):
            btn.configure(fg_color=_GREEN if i == idx else "transparent")

    def _raise_content(self, frame: ctk.CTkFrame) -> None:
        """Esconde todos os frames de conteúdo e exibe apenas o solicitado."""
        for f in (self._dashboard_frame, self._inventory_frame,
                  self._history_frame, self._breed_frame,
                  self._calc_frame, self._settings_frame,
                  self._admin_frame, self._dev_frame):
            if f is frame:
                f.grid(row=0, column=0, sticky="nsew")
            else:
                f.grid_remove()

    def _show_dashboard(self) -> None:
        self._nav_select(self._nav_idx.get("dashboard", 0))
        self._raise_content(self._dashboard_frame)
        threading.Thread(target=self._load_dashboard_data, daemon=True).start()

    def _show_inventory(self) -> None:
        self._nav_select(self._nav_idx.get("inventory", 1))
        self._raise_content(self._inventory_frame)
        threading.Thread(target=self._refresh_inventory, daemon=True).start()

    def _show_history(self) -> None:
        self._nav_select(self._nav_idx.get("history", 2))
        self._raise_content(self._history_frame)
        threading.Thread(target=self._load_history, daemon=True).start()

    def _show_settings(self) -> None:
        self._nav_select(self._nav_idx.get("settings", 5))
        self._raise_content(self._settings_frame)
        self._settings_url.delete(0, "end")
        self._settings_url.insert(0, self._cfg.config.backend_url)

    def _show_admin(self) -> None:
        self._nav_select(self._nav_idx.get("admin", 0))
        self._raise_content(self._admin_frame)
        threading.Thread(target=self._refresh_admin, daemon=True).start()

    def _show_dev(self) -> None:
        self._nav_select(self._nav_idx.get("dev", 0))
        self._raise_content(self._dev_frame)
        threading.Thread(target=self._refresh_health,      daemon=True).start()
        threading.Thread(target=self._load_dev_stats,      daemon=True).start()
        threading.Thread(target=self._refresh_dev_users,   daemon=True).start()
        threading.Thread(target=self._load_permissions,    daemon=True).start()
        threading.Thread(target=self._refresh_audit_logs,  daemon=True).start()
        threading.Thread(target=self._load_backend_config, daemon=True).start()
        threading.Thread(target=self._refresh_bot_status,  daemon=True).start()
        threading.Thread(target=self._refresh_bot_cogs,    daemon=True).start()
        threading.Thread(target=self._refresh_bot_logs,    daemon=True).start()
        threading.Thread(target=self._load_bot_config,     daemon=True).start()

    # ─── Sistema de Atualização ───────────────────────────────────────────

    def _check_updates_on_start(self) -> None:
        self._update_checker.check_async(
            on_result=lambda info: self._root.after(0, lambda: self._on_update_result(info))
        )

    def _on_update_result(self, info) -> None:
        current = self._update_checker.current_version
        if info and info.is_newer_than(current):
            self._update_info = info
            msg = f"🔔  Nova versão disponível: v{info.version} — clique para atualizar"
            # Banner na tela de login (place no topo, largura total)
            self._login_update_lbl.configure(text=msg)
            self._login_update_banner.place(x=0, y=0, relwidth=1)
            # Banner no dashboard (se já logado)
            self._update_banner_lbl.configure(text=f"🔔  Nova versão disponível: v{info.version}")
            self._update_banner.pack(fill="x", padx=24, pady=(0, 8))
            # Label na sidebar
            self._sidebar_update_lbl.configure(text=f"🔔 v{info.version}")
        else:
            self._login_update_banner.place_forget()
            self._update_banner.pack_forget()
            self._sidebar_update_lbl.configure(text="")

    def _do_update(self) -> None:
        if not self._update_info:
            return
        import tkinter.messagebox as mb
        info = self._update_info
        msg = (
            f"Atualizar para v{info.version}?\n\n"
            "O app será fechado, a atualização será baixada\n"
            "e o app reiniciará automaticamente."
        )
        if not mb.askyesno("Atualizar ARKLAND Player", msg):
            return
        try:
            self._update_checker.launch_updater(self._update_info)
        except Exception as exc:
            mb.showerror("Erro", f"Não foi possível iniciar o agente de atualização:\n{exc}")
            return
        # Fecha o app principal para o agente assumir
        self._root.after(300, self._root.destroy)

    # ─── Visibilidade de telas ────────────────────────────────────────────

    def _show_login(self) -> None:
        self._main_frame.grid_remove()
        self._login_frame.grid(row=0, column=0, sticky="nsew")

    def _show_main(self, role: str = "") -> None:
        self._login_frame.grid_remove()
        cfg = self._cfg.config
        if role:
            cfg.role = role
        self._api = ApiClient(cfg.backend_url, cfg.jwt_token)
        self._setup_nav(cfg.role)
        self._main_frame.grid(row=0, column=0, sticky="nsew")
        self._show_dashboard()

    # ─── Ações ────────────────────────────────────────────────────────────

    def _on_steam_login(self) -> None:
        url = self._cfg.config.backend_url
        if not url:
            self._login_status.configure(text="Configure a URL do backend na aba Dev.", text_color="#ff6b6b")
            return

        self._login_status.configure(text="Aguardando login no navegador...", text_color=_TEXT_DIM)
        self._login_btn.configure(state="disabled")

        def _on_success(jwt: str, steam_id: str, persona_name: str, role: str) -> None:
            self._cfg.config.jwt_token    = jwt
            self._cfg.config.steam_id     = steam_id
            self._cfg.config.persona_name = persona_name
            self._cfg.config.role         = role
            self._cfg.config.display_name = persona_name
            self._cfg.save()
            self._root.after(0, lambda: self._show_main(role))

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

    def _on_dev_login(self) -> None:
        username = self._dev_user_entry.get().strip()
        password = self._dev_pass_entry.get()
        if not username or not password:
            self._dev_login_status.configure(text="Preencha usuário e senha.", text_color="#ff6b6b")
            return
        self._dev_login_status.configure(text="")
        self._dev_login_btn.configure(state="disabled")
        _local_url = self._dev_url_entry.get().strip().rstrip("/") or f"http://127.0.0.1:{ServerManager.PORT}"
        api = ApiClient(_local_url)

        def _do():
            result, err = api.dev_login(username, password)

            def _update():
                self._dev_login_btn.configure(state="normal")
                if result:
                    self._cfg.config.jwt_token    = result["access_token"]
                    self._cfg.config.role         = result.get("role", "dev")
                    self._cfg.config.display_name = username
                    self._cfg.config.backend_url  = _local_url
                    self._cfg.save()
                    self._show_main(self._cfg.config.role)
                else:
                    self._dev_login_status.configure(text=err or "Servidor não disponível.", text_color="#ff6b6b")
            self._root.after(0, _update)

        threading.Thread(target=_do, daemon=True).start()

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

    def _refresh_admin(self) -> None:
        if not self._api:
            return
        players = self._api.get_all_players()

        def _update():
            for row in self._admin_tree.get_children():
                self._admin_tree.delete(row)
            for p in players:
                dt = self._fmt_date(p.get("last_seen", ""))
                self._admin_tree.insert("", "end", values=(
                    p.get("persona_name", "—"),
                    p.get("steam_id", ""),
                    p.get("permission_group", "player"),
                    dt,
                ))
        self._root.after(0, _update)

    def _load_dev_stats(self) -> None:
        if not self._api:
            return
        stats = self._api.get_database_stats()

        def _update():
            if stats:
                self._dev_stat_players.configure(text=str(stats.get("players", "–")))
                self._dev_stat_snapshots.configure(text=str(stats.get("inventory_snapshots", "–")))
                self._dev_stat_items.configure(text=str(stats.get("inventory_items", "–")))
                self._dev_stat_devusers.configure(text=str(stats.get("dev_users", "–")))
                self._dev_stat_logs.configure(text=str(stats.get("audit_logs", "–")))
        self._root.after(0, _update)

    def _create_dev_user(self) -> None:
        username = self._new_dev_user.get().strip()
        password = self._new_dev_pass.get()
        if not username or not password:
            self._dev_frame_status.configure(text="Preencha usuário e senha.", text_color="#ff6b6b")
            return
        self._dev_frame_status.configure(text="Criando...", text_color=_TEXT_DIM)

        def _do():
            result = self._api.create_dev_user(username, password) if self._api else None

            def _update():
                if result:
                    self._new_dev_user.delete(0, "end")
                    self._new_dev_pass.delete(0, "end")
                    self._dev_frame_status.configure(text=f"Usuário '{username}' criado.", text_color=_GREEN)
                    threading.Thread(target=self._refresh_dev_users, daemon=True).start()
                else:
                    self._dev_frame_status.configure(text="Erro ao criar usuário.", text_color="#ff6b6b")
            self._root.after(0, _update)

        threading.Thread(target=_do, daemon=True).start()

    # ─── Dev: Status ──────────────────────────────────────────────────────

    def _refresh_health(self) -> None:
        if not self._api:
            return
        status = self._api.get_health_status()

        def _update():
            if not status:
                for attr in ("_health_backend_lbl", "_health_db_lbl", "_health_steam_lbl", "_health_uptime_lbl"):
                    getattr(self, attr).configure(text="Erro", text_color="#ff6b6b")
                return

            def _color(s: str) -> str:
                return _GREEN if s == "ok" else ("#cc8833" if s == "not_configured" else "#ff6b6b")

            self._health_backend_lbl.configure(text="✔ Online", text_color=_GREEN)

            db_s = status.get("database", "error")
            self._health_db_lbl.configure(
                text="✔ Online" if db_s == "ok" else "✘ Erro",
                text_color=_color(db_s),
            )

            steam_s = status.get("steam_api", "error")
            steam_txt = {"ok": "✔ Online", "not_configured": "⚠ Não config.", "error": "✘ Erro"}.get(steam_s, steam_s)
            self._health_steam_lbl.configure(text=steam_txt, text_color=_color(steam_s))

            uptime = int(status.get("uptime_seconds", 0))
            h, rem = divmod(uptime, 3600)
            m = rem // 60
            self._health_uptime_lbl.configure(text=f"{h}h {m:02d}m", text_color=_TEXT)

        self._root.after(0, _update)

    # ─── Dev: Usuários Dev ────────────────────────────────────────────────

    def _refresh_dev_users(self) -> None:
        if not self._api:
            return
        users = self._api.get_dev_users()

        def _update():
            for w in self._dev_users_scroll.winfo_children():
                w.destroy()
            if not users:
                ctk.CTkLabel(
                    self._dev_users_scroll,
                    text="Nenhum usuário Dev cadastrado.",
                    font=_FONT_SM, text_color=_TEXT_DIM,
                ).pack(pady=16)
                return
            for u in users:
                row = ctk.CTkFrame(self._dev_users_scroll, fg_color=_BG_MAIN, corner_radius=8)
                row.pack(fill="x", pady=2)
                row.grid_columnconfigure(0, weight=1)
                ctk.CTkLabel(row, text=u["username"], font=("Segoe UI", 12, "bold"), text_color=_TEXT).grid(
                    row=0, column=0, padx=12, pady=(6, 2), sticky="w",
                )
                dt = self._fmt_date(u.get("created_at", ""))
                ctk.CTkLabel(row, text=f"Criado em {dt}", font=_FONT_SM, text_color=_TEXT_DIM).grid(
                    row=1, column=0, padx=12, pady=(0, 6), sticky="w",
                )
                if u["username"] != self._cfg.config.display_name:
                    uid = u["id"]
                    ctk.CTkButton(
                        row, text="🗑", width=30, height=28,
                        fg_color="#3a1a1a", hover_color="#5a2020",
                        font=_FONT_SM, text_color="#ff6b6b", corner_radius=6,
                        command=lambda i=uid: self._delete_dev_user(i),
                    ).grid(row=0, column=1, padx=8, pady=6, rowspan=2)

        self._root.after(0, _update)

    def _delete_dev_user(self, user_id: int) -> None:
        def _do():
            success = self._api.delete_dev_user(user_id) if self._api else False
            if success:
                threading.Thread(target=self._refresh_dev_users, daemon=True).start()
            else:
                self._root.after(0, lambda: self._dev_frame_status.configure(
                    text="Erro ao remover usuário.", text_color="#ff6b6b",
                ))
        threading.Thread(target=_do, daemon=True).start()

    # ─── Dev: Permissões ARK ──────────────────────────────────────────────

    def _load_permissions(self) -> None:
        if not self._api:
            return
        data = self._api.get_permissions()

        def _update():
            if data:
                groups = data.get("admin_groups", [])
                self._perm_admin_groups_entry.delete(0, "end")
                self._perm_admin_groups_entry.insert(0, ", ".join(groups))
        self._root.after(0, _update)

    def _save_permissions(self) -> None:
        raw = self._perm_admin_groups_entry.get().strip()
        groups = [g.strip() for g in raw.split(",") if g.strip()]
        if not groups:
            self._perm_status_lbl.configure(text="Informe ao menos um grupo.", text_color="#ff6b6b")
            return

        def _do():
            result = self._api.update_permissions(groups) if self._api else None

            def _update():
                if result:
                    self._perm_status_lbl.configure(text="✔ Permissões salvas.", text_color=_GREEN)
                else:
                    self._perm_status_lbl.configure(text="Erro ao salvar.", text_color="#ff6b6b")
            self._root.after(0, _update)
        threading.Thread(target=_do, daemon=True).start()

    # ─── Dev: Banco de Dados ──────────────────────────────────────────────

    def _cleanup_database(self) -> None:
        try:
            days = int(self._cleanup_days_entry.get())
        except ValueError:
            self._db_cleanup_status.configure(text="Informe um número válido de dias.", text_color="#ff6b6b")
            return
        self._db_cleanup_status.configure(text="Limpando...", text_color=_TEXT_DIM)

        def _do():
            result = self._api.cleanup_database(days) if self._api else None

            def _update():
                if result:
                    deleted = result.get("deleted_snapshots", 0)
                    self._db_cleanup_status.configure(
                        text=f"✔ {deleted} snapshot(s) removido(s).", text_color=_GREEN,
                    )
                    threading.Thread(target=self._load_dev_stats, daemon=True).start()
                else:
                    self._db_cleanup_status.configure(text="Erro ao executar limpeza.", text_color="#ff6b6b")
            self._root.after(0, _update)
        threading.Thread(target=_do, daemon=True).start()

    # ─── Dev: Logs de Auditoria ───────────────────────────────────────────

    def _refresh_audit_logs(self) -> None:
        if not self._api:
            return
        logs = self._api.get_audit_logs()

        def _update():
            for row in self._audit_tree.get_children():
                self._audit_tree.delete(row)
            for log in logs:
                dt = self._fmt_date(log.get("timestamp", ""))
                self._audit_tree.insert("", "end", values=(
                    dt,
                    log.get("event_type", ""),
                    log.get("identifier", ""),
                    log.get("role_assigned") or "–",
                    log.get("ip_address") or "–",
                ))
        self._root.after(0, _update)

    # ─── Dev: Configurações do Backend ────────────────────────────────────

    def _load_backend_config(self) -> None:
        if not self._api:
            return
        config = self._api.get_backend_config()

        def _update():
            if not config:
                return
            import json as _json
            for key, entry in self._cfg_entries.items():
                value = config.get(key)
                if value is not None:
                    entry.delete(0, "end")
                    entry.insert(0, _json.dumps(value) if isinstance(value, (list, dict)) else str(value))
        self._root.after(0, _update)

    def _save_backend_config(self) -> None:
        self._config_status_lbl.configure(text="Salvando...", text_color=_TEXT_DIM)

        def _do():
            errors: list[str] = []
            for key, entry in self._cfg_entries.items():
                value = entry.get().strip()
                if not value:
                    continue
                result = self._api.update_backend_config(key, value) if self._api else None
                if not result:
                    errors.append(key)

            def _update():
                if errors:
                    self._config_status_lbl.configure(
                        text=f"Erro em: {', '.join(errors)}", text_color="#ff6b6b",
                    )
                else:
                    self._config_status_lbl.configure(text="✔ Configurações salvas.", text_color=_GREEN)
            self._root.after(0, _update)
        threading.Thread(target=_do, daemon=True).start()

    # ─── Utilitários ──────────────────────────────────────────────────────

    @staticmethod
    def _fmt_date(iso: str) -> str:
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return iso

    # ─── Navegação: Breeding / Calculadora ────────────────────────────────

    def _show_breed(self) -> None:
        self._nav_select(self._nav_idx.get("breed", 3))
        self._raise_content(self._breed_frame)
        self._refresh_breed_list()

    def _show_calc(self) -> None:
        self._nav_select(self._nav_idx.get("calc", 4))
        self._raise_content(self._calc_frame)

    # ─── Breed: ações ─────────────────────────────────────────────────────

    def _refresh_breed_list(self) -> None:
        for w in self._breed_list_scroll.winfo_children():
            w.destroy()

        machos  = [d for d in self._breed.dinos if d.gender == "Macho"]
        femeas  = [d for d in self._breed.dinos if d.gender == "Fêmea"]
        options_m = [f"{d.name} (Lv{d.level})" for d in machos] or ["—"]
        options_f = [f"{d.name} (Lv{d.level})" for d in femeas] or ["—"]
        self._breed_male_cb.configure(values=options_m)
        self._breed_female_cb.configure(values=options_f)
        self._breed_male_cb.set(options_m[0])
        self._breed_female_cb.set(options_f[0])
        self._breed_machos = machos
        self._breed_femeas = femeas

        if not self._breed.dinos:
            ctk.CTkLabel(self._breed_list_scroll, text="Nenhum dino cadastrado.\nClique em '+ Adicionar Dino'.",
                font=_FONT_SM, text_color=_TEXT_DIM, justify="center").pack(pady=24)
            return

        for dino in self._breed.dinos:
            card = ctk.CTkFrame(self._breed_list_scroll, fg_color=_BG_MAIN, corner_radius=8)
            card.pack(fill="x", pady=4, padx=4)
            card.grid_columnconfigure(0, weight=1)

            icon = "♂" if dino.gender == "Macho" else "♀"
            color = "#7ec8e3" if dino.gender == "Macho" else "#f4a0c0"
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 2))
            ctk.CTkLabel(top, text=f"{icon} {dino.name}", font=("Segoe UI", 12, "bold"),
                text_color=color).pack(side="left")
            ctk.CTkLabel(top, text=f"Lv {dino.level}", font=_FONT_SM,
                text_color=_TEXT_DIM).pack(side="right")

            ctk.CTkLabel(card, text=dino.species or "—", font=_FONT_SM, text_color=_TEXT_DIM).grid(row=1, column=0, padx=8, sticky="w")

            stats_row = ctk.CTkFrame(card, fg_color="transparent")
            stats_row.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=(2, 4))
            for key in STAT_KEYS:
                val = getattr(dino, key, 0)
                lbl = ctk.CTkLabel(stats_row, text=f"{STAT_LABELS[key][0]}:{val}",
                    font=("Segoe UI", 9), text_color=_TEXT_DIM)
                lbl.pack(side="left", padx=3)

            dino_id = dino.id
            ctk.CTkButton(card, text="🗑", width=30, height=24,
                fg_color="#3a1a1a", hover_color="#5a2020",
                font=_FONT_SM, text_color="#ff6b6b", corner_radius=6,
                command=lambda did=dino_id: self._delete_dino(did),
            ).grid(row=0, column=1, padx=8, pady=(8, 2))

    def _delete_dino(self, dino_id: str) -> None:
        self._breed.remove(dino_id)
        self._refresh_breed_list()

    def _open_add_dino_dialog(self) -> None:
        dlg = ctk.CTkToplevel(self._root)
        dlg.title("Adicionar Dino")
        dlg.geometry("420x620")
        dlg.configure(fg_color=_BG_MAIN)
        dlg.grab_set()
        dlg.resizable(False, False)

        ctk.CTkLabel(dlg, text="Novo Dino", font=_FONT_TITLE, text_color=_TEXT).pack(pady=(20, 8))

        form = ctk.CTkFrame(dlg, fg_color=_BG_CARD, corner_radius=12)
        form.pack(fill="x", padx=20, pady=4)

        fields: dict = {}
        rows = [("Nome", "name"), ("Espécie", "species"), ("Nível", "level")]
        for label, key in rows:
            ctk.CTkLabel(form, text=label, font=_FONT_SM, text_color=_TEXT_DIM).pack(anchor="w", padx=16, pady=(10, 0))
            e = ctk.CTkEntry(form, height=32, fg_color=_BG_INPUT, border_color=_GREEN,
                corner_radius=6, font=_FONT, text_color=_TEXT)
            e.pack(fill="x", padx=16, pady=(2, 0))
            fields[key] = e

        ctk.CTkLabel(form, text="Gênero", font=_FONT_SM, text_color=_TEXT_DIM).pack(anchor="w", padx=16, pady=(10, 0))
        gender_var = ctk.CTkOptionMenu(form, values=["Macho", "Fêmea"],
            fg_color=_BG_INPUT, button_color=_GREEN, button_hover_color=_GREEN_HOVER,
            font=_FONT, text_color=_TEXT)
        gender_var.pack(fill="x", padx=16, pady=(2, 12))

        ctk.CTkLabel(dlg, text="Pontos Wild por stat", font=_FONT_SM, text_color=_TEXT_DIM).pack(anchor="w", padx=20, pady=(12, 4))
        stats_frame = ctk.CTkFrame(dlg, fg_color=_BG_CARD, corner_radius=12)
        stats_frame.pack(fill="x", padx=20, pady=0)

        stat_entries: dict = {}
        cols = 4
        for idx, key in enumerate(STAT_KEYS):
            r, c = divmod(idx, cols)
            ctk.CTkLabel(stats_frame, text=STAT_LABELS[key], font=("Segoe UI", 9), text_color=_TEXT_DIM).grid(
                row=r * 2, column=c, padx=8, pady=(8, 0))
            se = ctk.CTkEntry(stats_frame, width=60, height=28, fg_color=_BG_INPUT,
                border_color=_GREEN, corner_radius=6, font=_FONT_SM, text_color=_TEXT)
            se.insert(0, "0")
            se.grid(row=r * 2 + 1, column=c, padx=8, pady=(0, 8))
            stat_entries[key] = se

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=16)

        def _save():
            try:
                lvl = int(fields["level"].get() or 0)
            except ValueError:
                lvl = 0
            dino = Dino(
                name=fields["name"].get().strip() or "Sem Nome",
                species=fields["species"].get().strip(),
                gender=gender_var.get(),
                level=lvl,
                **{k: int(stat_entries[k].get() or 0) for k in STAT_KEYS},
            )
            self._breed.add(dino)
            self._refresh_breed_list()
            dlg.destroy()

        ctk.CTkButton(btn_row, text="Salvar", height=38,
            fg_color=_GREEN, hover_color=_GREEN_HOVER,
            font=("Segoe UI", 12, "bold"), text_color="#000", corner_radius=8,
            command=_save).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(btn_row, text="Cancelar", height=38,
            fg_color=_BG_CARD, hover_color="#2a2a45",
            font=_FONT, text_color=_TEXT, corner_radius=8,
            command=dlg.destroy).pack(side="left", fill="x", expand=True)

    def _simulate_breed(self) -> None:
        for w in self._breed_result_frame.winfo_children():
            w.destroy()

        male_idx  = self._breed_male_cb.current() if hasattr(self._breed_male_cb, "current") else 0
        female_idx = self._breed_female_cb.current() if hasattr(self._breed_female_cb, "current") else 0

        male_list  = getattr(self, "_breed_machos", [])
        female_list = getattr(self, "_breed_femeas", [])

        if not male_list or not female_list:
            ctk.CTkLabel(self._breed_result_frame, text="Cadastre ao menos um macho e uma fêmea.",
                font=_FONT_SM, text_color="#ff6b6b").pack(padx=12, pady=16)
            return

        male_idx   = min(male_idx, len(male_list) - 1)
        female_idx = min(female_idx, len(female_list) - 1)
        offspring  = self._breed.best_offspring(male_list[male_idx].id, female_list[female_idx].id)

        if not offspring:
            return

        ctk.CTkLabel(self._breed_result_frame, text="Melhor Offspring (wild pts):",
            font=("Segoe UI", 11, "bold"), text_color=_TEXT).pack(anchor="w", padx=12, pady=(10, 4))

        grid = ctk.CTkFrame(self._breed_result_frame, fg_color="transparent")
        grid.pack(fill="x", padx=12, pady=(0, 10))
        for col, key in enumerate(STAT_KEYS):
            ctk.CTkLabel(grid, text=STAT_LABELS[key], font=("Segoe UI", 9), text_color=_TEXT_DIM).grid(row=0, column=col, padx=6)
            ctk.CTkLabel(grid, text=str(offspring.get(key, 0)),
                font=("Segoe UI", 13, "bold"), text_color=_GREEN).grid(row=1, column=col, padx=6)

    # ─── Calculadora: ações ───────────────────────────────────────────────

    def _recalc_stats(self) -> None:
        try:
            wild_mult = float(self._calc_wild_mult.get() or 1)
        except ValueError:
            wild_mult = 1.0
        try:
            dom_mult = float(self._calc_dom_mult.get() or 1)
        except ValueError:
            dom_mult = 1.0

        for key, row in self._calc_entries.items():
            try:
                base      = float(row["base"].get() or 0)
                wild_pts  = float(row["wild_pts"].get() or 0)
                wild_inc  = float(row["wild_inc"].get() or 0)
                dom_pts   = float(row["dom_pts"].get() or 0)
                dom_inc   = float(row["dom_inc"].get() or 0)
                result = base * (1 + wild_pts * wild_inc * wild_mult) * (1 + dom_pts * dom_inc * dom_mult)
                row["result"].configure(text=f"{result:,.1f}")
            except (ValueError, ZeroDivisionError):
                row["result"].configure(text="—")

    def _reset_calc(self) -> None:
        self._calc_wild_mult.delete(0, "end")
        self._calc_wild_mult.insert(0, "1.0")
        self._calc_dom_mult.delete(0, "end")
        self._calc_dom_mult.insert(0, "1.0")
        for key, row in self._calc_entries.items():
            wild_inc_def, dom_inc_def = STAT_DEFAULTS[key]
            row["base"].delete(0, "end")
            row["wild_pts"].delete(0, "end")
            row["wild_pts"].insert(0, "0")
            row["wild_inc"].delete(0, "end")
            row["wild_inc"].insert(0, f"{wild_inc_def:.2f}")
            row["dom_pts"].delete(0, "end")
            row["dom_pts"].insert(0, "0")
            row["dom_inc"].delete(0, "end")
            row["dom_inc"].insert(0, f"{dom_inc_def:.2f}")
            row["result"].configure(text="—")

    def run(self) -> None:
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.mainloop()

    def _on_close(self) -> None:
        """Para o servidor backend (se ativo) antes de fechar o app."""
        self._srv_mgr.stop()
        self._root.destroy()
