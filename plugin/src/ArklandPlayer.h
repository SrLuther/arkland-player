#pragma once
// ============================================================
//  ArklandPlayer.h
//  Plugin para ARK: Survival Evolved (ArkServerApi)
//  Comandos: /u (upload inventário) | /dow (download inventário)
// ============================================================
#include <API/ARK/Ark.h>
#include <ArkApi/PluginManager.h>
#include <Permissions.h>   // ArkServerApi PermissionsManager plugin
#include <fstream>
#include <string>
#include <vector>

// nlohmann/json — inclua o header-only em plugin/thirdparty/json.hpp
// Download: https://github.com/nlohmann/json/releases/latest
#include "../thirdparty/json.hpp"
using json = nlohmann::json;

#include "HttpClient.h"

// ─── Configuração carregada de ArklandPlayer.json ─────────────────────────
struct PluginConfig
{
    std::wstring backend_host  = L"localhost";
    int          backend_port  = 5000;
    std::wstring backend_path  = L"";          // prefixo de path, ex: L"/api"
    std::string  server_api_key;
    std::string  server_name   = "ARK Server";
    std::string  map_name      = "TheIsland";
    // Grupos do PermissionsManager que podem usar /u e /dow
    std::vector<std::string> allowed_groups = {"admin", "mod", "vip", "player"};
};

namespace Plugin
{
    void Init();
    void Unload();

    void LoadConfig();
    bool IsAllowed(APlayerController* player_controller);

    // Handlers dos comandos de chat
    void CommandUpload  (AShooterPlayerController* player_controller, FString* msg, EChatSendMode::Type mode);
    void CommandDownload(AShooterPlayerController* player_controller, FString* msg, EChatSendMode::Type mode);

    // Utilitários
    std::string GetSteamId(AShooterPlayerController* pc);
    void SendMsg(AShooterPlayerController* pc, const FString& text);

    inline PluginConfig Config;
}
