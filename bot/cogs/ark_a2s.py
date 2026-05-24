# cogs/ark_a2s.py
# Monitoramento A2S (Steam Query) + integração Steam API para servidores ARK
#
# Baseado em: https://github.com/chicken647/Ark-Server-Monitoring-Bot (MIT License)
# Adaptado e integrado ao projeto oBobonicClean
#
# Funcionalidades:
#   - /serverstatus       → status A2S de todos/um servidor (funciona sem RCON)
#   - /steamprofile       → perfil Steam de um jogador via SteamID64
#   - /steamrecent        → jogos ARK recentes de um jogador via Steam API
#   - Loop automático     → notificações de entrada de jogadores a cada 60s

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import a2s
import discord
import requests  # type: ignore[import]
from discord.ext import commands, tasks

import config

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# PERSISTÊNCIA DE CONTAGEM DE ENTRADAS
# ─────────────────────────────────────────────────────────────

_JOIN_COUNTS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "a2s_join_counts.json")
_STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "a2s_state.json")


def _load_state() -> dict:
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(data: dict) -> None:
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_join_counts() -> dict:
    try:
        with open(_JOIN_COUNTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_join_counts(data: dict) -> None:
    os.makedirs(os.path.dirname(_JOIN_COUNTS_FILE), exist_ok=True)
    with open(_JOIN_COUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────
# HELPERS A2S
# ─────────────────────────────────────────────────────────────

async def _a2s_info(host: str, port: int, timeout: float = 5.0) -> a2s.SourceInfo:
    """Consulta informações do servidor via Steam Query (A2S_INFO)."""
    def _query():
        return a2s.info((host, port), timeout=timeout)
    return await asyncio.to_thread(_query)


async def _a2s_players(host: str, port: int, timeout: float = 5.0) -> list:
    """Consulta lista de jogadores via Steam Query (A2S_PLAYER)."""
    def _query():
        return a2s.players((host, port), timeout=timeout)
    return await asyncio.to_thread(_query)


def _format_duration(seconds: float) -> str:
    """Formata segundos em hh:mm ou mm:ss."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


# ─────────────────────────────────────────────────────────────
# HELPERS STEAM API
# ─────────────────────────────────────────────────────────────

def _steam_get(endpoint: str, params: dict) -> Optional[dict]:
    """Requisição GET síncrona à Steam Web API (use com asyncio.to_thread)."""
    if not config.STEAM_API_KEY:
        return None
    params = {**params, "key": config.STEAM_API_KEY, "format": "json"}
    try:
        r = requests.get(
            f"https://api.steampowered.com/{endpoint}",
            params=params,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"[A2S] Steam API erro ({endpoint}): {e}")
        return None


def _validate_steamid(steamid: str) -> bool:
    """Verifica se o SteamID64 é válido (17 dígitos numéricos)."""
    return steamid.isdigit() and len(steamid) == 17


# ─────────────────────────────────────────────────────────────
# VIEW — SELECT DE SERVIDOR
# ─────────────────────────────────────────────────────────────

class ServerSelectMenu(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=info["name"],
                value=key,
                emoji="🗺️",
                description=f"Query port: {info.get('query_port') or 'N/A'}",
            )
            for key, info in config.ARK_MAPS.items()
        ]
        super().__init__(
            placeholder="🔍 Selecione um servidor para ver detalhes...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ark_server_select",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)

        map_key = self.values[0]
        map_info = config.ARK_MAPS.get(map_key)
        if not map_info:
            await interaction.followup.send("❌ Servidor não encontrado.", ephemeral=True)
            return

        server_name = map_info["name"]
        query_port = map_info.get("query_port")
        max_players = map_info.get("max_players", 50)
        host = map_info["host"]
        bm_id = map_info.get("battlemetrics_id", "")
        bm_url = f"https://www.battlemetrics.com/servers/ark/{bm_id}" if bm_id else None

        embed = discord.Embed(
            title=f"📡 {server_name}",
            url=bm_url,
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )

        if query_port:
            try:
                info = await _a2s_info(host, query_port)
                players = await _a2s_players(host, query_port)

                embed.color = discord.Color.green()
                embed.add_field(name="🟢 Status", value="**Online**", inline=True)
                embed.add_field(
                    name="👥 Jogadores",
                    value=f"`{info.player_count}/{max_players}`",
                    inline=True,
                )
                embed.add_field(name="🗺️ Mapa", value=f"`{info.map_name}`", inline=True)
                embed.add_field(name="🏷️ Nome Steam", value=f"`{info.server_name}`", inline=False)

                if players:
                    sorted_players = sorted(players, key=lambda p: p.duration, reverse=True)
                    player_lines = "\n".join(
                        f"  🦕 `{p.name}` — _{_format_duration(p.duration)}_"
                        for p in sorted_players[:15]
                    )
                    if len(players) > 15:
                        player_lines += f"\n  _...+{len(players) - 15} outros_"
                    embed.add_field(name="🎮 Jogadores online", value=player_lines, inline=False)
                else:
                    embed.add_field(
                        name="🎮 Jogadores online",
                        value="_Nenhum jogador conectado_",
                        inline=False,
                    )
            except Exception:
                embed.color = discord.Color.red()
                embed.add_field(
                    name="🔴 Status",
                    value="**Offline** — sem resposta A2S",
                    inline=False,
                )
        else:
            embed.add_field(
                name="⚠️ Configuração",
                value="`query_port` não definido no `.env`",
                inline=False,
            )

        if bm_id:
            banner_url = (
                f"https://cdn.battlemetrics.com/b/horizontal500x80px/{bm_id}.png"
                "?foreground=%23EEEEEE&background=%23222222&lines=%23333333"
                "&linkColor=%231185ec&chartColor=%23FF0700"
            )
            embed.set_image(url=banner_url)

        embed.set_footer(text="Steam Query Protocol (A2S) • não requer RCON")
        await interaction.followup.send(embed=embed, ephemeral=True)


class ServerSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ServerSelectMenu())
        self.add_item(RefreshButton())


class RefreshButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Atualizar",
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
            custom_id="ark_status_refresh",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("❌ Canal inválido.", ephemeral=True)
            return

        # Encontra o cog A2S para chamar _update_status_panel
        cog = interaction.client.cogs.get("ArkA2S")
        if cog:
            await cog._update_status_panel(channel)  # type: ignore[union-attr]
            await interaction.followup.send("✅ Painel atualizado!", ephemeral=True)
        else:
            await interaction.followup.send("❌ Cog A2S não encontrado.", ephemeral=True)


# ─────────────────────────────────────────────────────────────
# COG
# ─────────────────────────────────────────────────────────────

class ArkA2S(commands.Cog):
    """Monitoramento A2S de servidores ARK e integração com Steam API."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # {map_key: set(player_names)} — jogadores online por servidor (rastreio por nome)
        self._online_players: dict[str, set] = {}
        # {map_key: {player_name: join_count}} — persistido em JSON
        self._join_counts: dict[str, dict[str, int]] = _load_join_counts()
        # ID da mensagem de status fixo (editada a cada 10 min)
        _state = _load_state()
        self._status_message_id: Optional[int] = _state.get("status_message_id")
        # ID da mensagem de última ação (editada a cada evento de entrada/saída)
        self._last_event_message_id: Optional[int] = _state.get("last_event_message_id")

    async def cog_load(self) -> None:
        # Registra a view persistente para sobreviver a reinicializações
        self.bot.add_view(ServerSelectView())
        notifications_enabled = bool(config.ARK_JOIN_NOTIFICATIONS_CHANNEL_ID)
        has_maps_with_query = any(
            m.get("query_port") for m in config.ARK_MAPS.values()
        )
        if notifications_enabled and has_maps_with_query:
            self.join_monitor_loop.start()  # type: ignore[union-attr]
            logger.info("[A2S] Loop de monitoramento iniciado.")
        else:
            logger.info(
                "[A2S] Loops inativos "
                "(ARK_JOIN_NOTIFICATIONS_CHANNEL_ID=0 ou nenhum query_port configurado)."
            )

    async def cog_unload(self) -> None:
        if self.join_monitor_loop.is_running():  # type: ignore[union-attr]
            self.join_monitor_loop.cancel()  # type: ignore[union-attr]

    # ─────────────────────────────────────────────────────────────
    # SCAN INICIAL — executado uma vez ao ligar o bot
    # ─────────────────────────────────────────────────────────────

    async def _startup_scan(self) -> None:
        """
        Escaneia todos os servidores ao iniciar o bot:
        - Coleta status, jogadores e contagem
        - Inicializa _online_players (evita falsos alertas de entrada)
        - Edita o painel de status existente ou cria um novo
        """
        print("[A2S] 🔍 Scan inicial de servidores...")

        channel = self.bot.get_channel(config.ARK_JOIN_NOTIFICATIONS_CHANNEL_ID)

        embed = discord.Embed(
            title="📊 Status dos Servidores — Atualização Automática",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )

        total_players = 0
        servers_online = 0

        for map_key, map_info in config.ARK_MAPS.items():
            query_port = map_info.get("query_port")
            server_name = map_info["name"]
            max_players = map_info.get("max_players", 50)

            if not query_port:
                self._online_players[map_key] = set()
                embed.add_field(
                    name=f"🔶 {server_name}",
                    value="⚠️ `query_port` não configurado",
                    inline=True,
                )
                continue

            host = map_info["host"]
            try:
                info = await _a2s_info(host, query_port)
                players = await _a2s_players(host, query_port)

                current_names: set = {p.name for p in players if p.name}
                # Registra jogadores já online para NÃO gerar alerta de entrada no 1º ciclo
                self._online_players[map_key] = current_names

                count = len(current_names)
                total_players += count
                servers_online += 1

                value = f"🟢 **Online** — `{count}/{max_players}`\n"
                if current_names:
                    listed = sorted(current_names)[:6]
                    value += "\n".join(f"  • `{n}`" for n in listed)
                    if len(current_names) > 6:
                        value += f"\n  _...+{len(current_names) - 6} outros_"
                else:
                    value += "_Nenhum jogador conectado_"

                embed.add_field(name=f"🗺️ {server_name}", value=value, inline=True)
                print(f"[A2S]   ✅ {server_name}: {count}/{max_players} jogadores")

            except Exception:
                self._online_players[map_key] = set()
                embed.add_field(
                    name=f"🗺️ {server_name}",
                    value="🔴 **Offline** — sem resposta A2S",
                    inline=True,
                )
                print(f"[A2S]   🔴 {server_name}: offline")

        embed.description = (
            f"**{servers_online}** servidor(es) online • "
            f"**{total_players}** jogador(es) conectados"
        )
        embed.set_footer(text="Atualiza a cada 60s • ARK Server Monitor • A2S")

        if isinstance(channel, discord.TextChannel):
            # Tenta editar a mensagem existente (evita duplicar)
            if self._status_message_id:
                try:
                    msg = await channel.fetch_message(self._status_message_id)
                    await msg.edit(embed=embed, view=ServerSelectView())
                    print(f"[A2S] ✅ Painel de startup editado (ID: {self._status_message_id})")
                except discord.NotFound:
                    self._status_message_id = None

            if not self._status_message_id:
                msg = await channel.send(embed=embed, view=ServerSelectView())
                self._status_message_id = msg.id
                _save_state({"status_message_id": self._status_message_id, "last_event_message_id": self._last_event_message_id})
                print(f"[A2S] ✅ Painel de startup criado (ID: {self._status_message_id})")

        # Inicia o loop de monitoramento (atualiza painel + detecta jogadores)
        if not self.join_monitor_loop.is_running():  # type: ignore[union-attr]
            pass  # já iniciado em cog_load via start()

        print(f"[A2S] ✅ Scan inicial concluído: {servers_online} online, {total_players} jogadores")

    # ─────────────────────────────────────────────────────────────
    # LOOP DE MONITORAMENTO — a cada 60s
    # ─────────────────────────────────────────────────────────────

    async def _send_or_edit_event(self, channel: discord.TextChannel, embed: discord.Embed) -> None:
        """Edita a mensagem de último evento ou cria uma nova se não existir."""
        if self._last_event_message_id:
            try:
                msg = await channel.fetch_message(self._last_event_message_id)
                await msg.edit(embed=embed)
                return
            except discord.NotFound:
                self._last_event_message_id = None
        msg = await channel.send(embed=embed)
        self._last_event_message_id = msg.id
        _save_state({"status_message_id": self._status_message_id, "last_event_message_id": self._last_event_message_id})

    @tasks.loop(seconds=60)
    async def join_monitor_loop(self):
        """
        A cada 60 s verifica cada servidor:
        - Detecta jogadores que entraram (por nome, não por contagem)
        - Detecta jogadores que saíram
        - Envia notificações de entrada com contagem histórica de visitas
        """
        channel = self.bot.get_channel(config.ARK_JOIN_NOTIFICATIONS_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            return

        for map_key, map_info in config.ARK_MAPS.items():
            query_port = map_info.get("query_port")
            if not query_port:
                continue

            host = map_info["host"]
            server_name = map_info["name"]
            max_players = map_info.get("max_players", 50)

            try:
                players = await _a2s_players(host, query_port)
                info = await _a2s_info(host, query_port)

                current_names: set = {p.name for p in players if p.name}
                previous_names: set = self._online_players.get(map_key, current_names)

                joined = current_names - previous_names
                left = previous_names - current_names

                # ── Notificações de ENTRADA ──
                for name in joined:
                    server_counts = self._join_counts.setdefault(map_key, {})
                    server_counts[name] = server_counts.get(name, 0) + 1
                    _save_join_counts(self._join_counts)

                    embed = discord.Embed(
                        title="🦕 Jogador entrou no servidor!",
                        color=discord.Color.green(),
                        timestamp=datetime.now(timezone.utc),
                    )
                    embed.add_field(name="👤 Jogador", value=f"`{name}`", inline=True)
                    embed.add_field(name="🗺️ Servidor", value=server_name, inline=True)
                    embed.add_field(
                        name="👥 Online agora",
                        value=f"`{len(current_names)}/{max_players}`",
                        inline=True,
                    )
                    embed.add_field(
                        name="🔢 Visitas registradas",
                        value=str(server_counts[name]),
                        inline=True,
                    )
                    embed.set_footer(text="ARK Server Monitor • A2S")
                    await self._send_or_edit_event(channel, embed)

                # ── Notificações de SAÍDA ──
                for name in left:
                    embed = discord.Embed(
                        title="👋 Jogador saiu do servidor",
                        color=discord.Color.orange(),
                        timestamp=datetime.now(timezone.utc),
                    )
                    embed.add_field(name="👤 Jogador", value=f"`{name}`", inline=True)
                    embed.add_field(name="🗺️ Servidor", value=server_name, inline=True)
                    embed.add_field(
                        name="👥 Online agora",
                        value=f"`{len(current_names)}/{max_players}`",
                        inline=True,
                    )
                    embed.set_footer(text="ARK Server Monitor • A2S")
                    await self._send_or_edit_event(channel, embed)

                self._online_players[map_key] = current_names

            except Exception:
                # Servidor offline — se havia jogadores, registra como saída em massa
                previous_names = self._online_players.get(map_key, set())
                if previous_names:
                    embed = discord.Embed(
                        title="🔴 Servidor ficou offline!",
                        color=discord.Color.red(),
                        timestamp=datetime.now(timezone.utc),
                    )
                    embed.add_field(name="🗺️ Servidor", value=server_name, inline=True)
                    embed.add_field(
                        name="👥 Jogadores afetados",
                        value=str(len(previous_names)),
                        inline=True,
                    )
                    embed.set_footer(text="ARK Server Monitor • A2S")
                    await self._send_or_edit_event(channel, embed)
                self._online_players[map_key] = set()

        # ── Atualiza o painel de status após processar todos os servidores ──
        await self._update_status_panel(channel)

    async def _update_status_panel(self, channel: discord.TextChannel) -> None:
        """Edita (ou cria) a mensagem de painel de status."""
        embed = discord.Embed(
            title="📊 Status dos Servidores — Atualização Automática",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        total_players = 0
        servers_online = 0

        for map_key, map_info in config.ARK_MAPS.items():
            query_port = map_info.get("query_port")
            server_name = map_info["name"]
            max_players = map_info.get("max_players", 50)

            if not query_port:
                embed.add_field(
                    name=f"🔶 {server_name}",
                    value="⚠️ `query_port` não configurado",
                    inline=True,
                )
                continue

            host = map_info["host"]
            current_names = self._online_players.get(map_key, set())
            count = len(current_names)
            total_players += count

            # Verifica se está online (tenta query rápida)
            try:
                await _a2s_info(host, query_port, timeout=3.0)
                servers_online += 1
                value = f"🟢 **Online** — `{count}/{max_players}`\n"
                if current_names:
                    listed = sorted(current_names)[:6]
                    value += "\n".join(f"  • `{n}`" for n in listed)
                    if len(current_names) > 6:
                        value += f"\n  _...+{len(current_names) - 6} outros_"
                else:
                    value += "_Nenhum jogador conectado_"
            except Exception:
                value = "🔴 **Offline** — sem resposta A2S"

            embed.add_field(name=f"🗺️ {server_name}", value=value, inline=True)

        embed.description = (
            f"**{servers_online}** servidor(es) online • "
            f"**{total_players}** jogador(es) conectados"
        )
        embed.set_footer(text="Atualiza a cada 60s • ARK Server Monitor • A2S")

        if self._status_message_id:
            try:
                msg = await channel.fetch_message(self._status_message_id)
                await msg.edit(embed=embed, view=ServerSelectView())
                return
            except discord.NotFound:
                self._status_message_id = None

        msg = await channel.send(embed=embed, view=ServerSelectView())
        self._status_message_id = msg.id
        _save_state({"status_message_id": self._status_message_id, "last_event_message_id": self._last_event_message_id})

    @join_monitor_loop.before_loop
    async def _before_join_monitor(self):
        await self.bot.wait_until_ready()
        await self._startup_scan()

    # ─────────────────────────────────────────────────────────────
    # AUTOCOMPLETE
    # ─────────────────────────────────────────────────────────────

    async def _autocomplete_servidor(
        self, interaction: discord.Interaction, current: str
    ) -> list[discord.app_commands.Choice[str]]:
        choices = [
            discord.app_commands.Choice(name=info["name"], value=key)
            for key, info in config.ARK_MAPS.items()
            if current.lower() in info["name"].lower() or current.lower() in key
        ]
        return choices[:25]

    # ─────────────────────────────────────────────────────────────
    # /serverstatus
    # ─────────────────────────────────────────────────────────────

    @discord.app_commands.command(
        name="serverstatus",
        description="Verifica o status dos servidores ARK via Steam Query (A2S) — funciona sem RCON",
    )
    @discord.app_commands.describe(servidor="Servidor específico (deixe vazio para todos)")
    @discord.app_commands.autocomplete(servidor=_autocomplete_servidor)
    async def serverstatus(
        self, interaction: discord.Interaction, servidor: Optional[str] = None
    ):
        await interaction.response.defer(thinking=True)

        # Filtra mapa(s) a consultar
        if servidor:
            maps_to_check = {
                k: v
                for k, v in config.ARK_MAPS.items()
                if k == servidor or servidor.lower() in v["name"].lower()
            }
            if not maps_to_check:
                await interaction.followup.send(
                    f"❌ Servidor `{servidor}` não encontrado.", ephemeral=True
                )
                return
        else:
            maps_to_check = config.ARK_MAPS

        if not maps_to_check:
            await interaction.followup.send(
                "❌ Nenhum servidor configurado em `ARK_MAPS`.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📡 Status dos Servidores — Steam Query (A2S)",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )

        for map_key, map_info in maps_to_check.items():
            query_port = map_info.get("query_port")
            server_name = map_info["name"]
            max_players = map_info.get("max_players", 50)

            if not query_port:
                embed.add_field(
                    name=f"🔶 {server_name}",
                    value="⚠️ `query_port` não configurado\n"
                    "Defina `ARK_MAP{N}_QUERY_PORT` no `.env`",
                    inline=False,
                )
                continue

            host = map_info["host"]
            try:
                info = await _a2s_info(host, query_port)
                players = await _a2s_players(host, query_port)

                player_lines = ""
                if players:
                    sorted_players = sorted(players, key=lambda p: p.duration, reverse=True)
                    player_lines = "\n".join(
                        f"  • `{p.name}` — {_format_duration(p.duration)}"
                        for p in sorted_players[:10]
                    )
                    if len(players) > 10:
                        player_lines += f"\n  ...e +{len(players) - 10} outros"

                value = (
                    f"🟢 **Online**\n"
                    f"🗺️ Mapa: `{info.map_name}`\n"
                    f"👥 Jogadores: `{info.player_count}/{max_players}`\n"
                    f"🏷️ Nome: `{info.server_name}`\n"
                )
                if player_lines:
                    value += f"**Jogadores:**\n{player_lines}"

            except Exception:
                value = "🔴 **Offline** — sem resposta A2S"

            embed.add_field(name=f"🗺️ {server_name}", value=value, inline=False)

        # Se for consulta de servidor único, adiciona banner do BattleMetrics
        if servidor and len(maps_to_check) == 1:
            bm_id = next(iter(maps_to_check.values())).get("battlemetrics_id", "")
            if bm_id:
                banner_url = (
                    f"https://cdn.battlemetrics.com/b/horizontal500x80px/{bm_id}.png"
                    "?foreground=%23EEEEEE&background=%23222222&lines=%23333333"
                    "&linkColor=%231185ec&chartColor=%23FF0700"
                )
                embed.set_image(url=banner_url)

        embed.set_footer(text="Steam Query Protocol (A2S) • não requer RCON")
        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────────────
    # /steamprofile
    # ─────────────────────────────────────────────────────────────

    @discord.app_commands.command(
        name="steamprofile",
        description="Consulta o perfil Steam de um jogador pelo SteamID64",
    )
    @discord.app_commands.describe(steamid="SteamID64 do jogador (17 dígitos numéricos)")
    async def steamprofile(self, interaction: discord.Interaction, steamid: str):
        await interaction.response.defer(thinking=True)

        if not _validate_steamid(steamid):
            await interaction.followup.send(
                "❌ SteamID inválido. Informe um SteamID64 com exatamente 17 dígitos numéricos.\n"
                "Exemplo: `76561198012345678`",
                ephemeral=True,
            )
            return

        if not config.STEAM_API_KEY:
            await interaction.followup.send(
                "❌ `STEAM_API_KEY` não configurada. Adicione ao seu `.env`.",
                ephemeral=True,
            )
            return

        data = await asyncio.to_thread(
            _steam_get,
            "ISteamUser/GetPlayerSummaries/v0002/",
            {"steamids": steamid},
        )

        if not data:
            await interaction.followup.send("❌ Erro ao consultar a Steam API.", ephemeral=True)
            return

        players = data.get("response", {}).get("players", [])
        if not players:
            await interaction.followup.send(
                f"❌ Nenhum perfil encontrado para o SteamID `{steamid}`.", ephemeral=True
            )
            return

        p = players[0]
        name = p.get("personaname", "Desconhecido")
        profile_url = p.get("profileurl", "")
        avatar_url = p.get("avatarfull", "")
        last_logoff = p.get("lastlogoff", 0)

        _status_map = {
            0: "⚫ Offline",
            1: "🟢 Online",
            2: "🔴 Ocupado",
            3: "🟡 Ausente",
            4: "😴 Cochilando",
            5: "💱 Buscando troca",
            6: "🎮 Buscando jogar",
        }
        status = _status_map.get(p.get("personastate", 0), "Desconhecido")

        embed = discord.Embed(
            title=f"🎮 Perfil Steam — {name}",
            url=profile_url,
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=avatar_url)
        embed.add_field(name="👤 Nome", value=name, inline=True)
        embed.add_field(name="🔵 Status", value=status, inline=True)
        embed.add_field(name="🆔 SteamID64", value=f"`{steamid}`", inline=True)
        embed.add_field(name="🔗 Perfil", value=profile_url or "—", inline=False)
        if last_logoff:
            embed.add_field(name="⏰ Último acesso", value=f"<t:{last_logoff}:R>", inline=True)

        embed.set_footer(text="Dados via Steam Web API")
        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────────────
    # /steamrecent
    # ─────────────────────────────────────────────────────────────

    @discord.app_commands.command(
        name="steamrecent",
        description="Mostra jogos ARK jogados recentemente por um jogador Steam",
    )
    @discord.app_commands.describe(steamid="SteamID64 do jogador (17 dígitos numéricos)")
    async def steamrecent(self, interaction: discord.Interaction, steamid: str):
        await interaction.response.defer(thinking=True)

        if not _validate_steamid(steamid):
            await interaction.followup.send(
                "❌ SteamID inválido. Informe um SteamID64 com exatamente 17 dígitos numéricos.",
                ephemeral=True,
            )
            return

        if not config.STEAM_API_KEY:
            await interaction.followup.send(
                "❌ `STEAM_API_KEY` não configurada. Adicione ao seu `.env`.",
                ephemeral=True,
            )
            return

        data = await asyncio.to_thread(
            _steam_get,
            "IPlayerService/GetRecentlyPlayedGames/v1/",
            {"steamid": steamid},
        )

        if not data:
            await interaction.followup.send("❌ Erro ao consultar a Steam API.", ephemeral=True)
            return

        games = data.get("response", {}).get("games", [])
        # ARK: Survival Evolved = 346110 | ARK: Survival Ascended = 2399830
        ark_games = [g for g in games if g.get("appid") in (346110, 2399830)]

        if not ark_games:
            await interaction.followup.send(
                f"ℹ️ Nenhum jogo ARK jogado recentemente encontrado para o SteamID `{steamid}`."
            )
            return

        embed = discord.Embed(
            title=f"🦕 ARK Recentes — `{steamid}`",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc),
        )

        for game in ark_games:
            playtime_2w = game.get("playtime_2weeks", 0)
            playtime_total = game.get("playtime_forever", 0)
            game_name = game.get("name", f"AppID {game.get('appid')}")
            embed.add_field(
                name=f"🎮 {game_name}",
                value=(
                    f"⏱️ Últimas 2 semanas: `{playtime_2w // 60}h {playtime_2w % 60}m`\n"
                    f"📊 Total jogado: `{playtime_total // 60}h`"
                ),
                inline=False,
            )

        embed.set_footer(text="Dados via Steam Web API")
        await interaction.followup.send(embed=embed)


# ─────────────────────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot):
    await bot.add_cog(ArkA2S(bot))
