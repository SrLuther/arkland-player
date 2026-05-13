// ============================================================
//  ArklandPlayer.cpp
//  Plugin para ARK: Survival Evolved (ArkServerApi)
// ============================================================
#include "ArklandPlayer.h"

// ─── DllMain ──────────────────────────────────────────────────────────────
BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason, LPVOID)
{
    switch (ul_reason)
    {
        case DLL_PROCESS_ATTACH:
            Plugin::Init();
            break;
        case DLL_PROCESS_DETACH:
            Plugin::Unload();
            break;
    }
    return TRUE;
}

// ─── Init / Unload ────────────────────────────────────────────────────────
void Plugin::Init()
{
    LoadConfig();

    ArkApi::GetCommands().AddChatCommand("/u",   &CommandUpload);
    ArkApi::GetCommands().AddChatCommand("/dow",  &CommandDownload);

    Log::GetLog()->info("[ArklandPlayer] Plugin carregado. Servidor: {} | Backend: {}:{}",
        Config.server_name,
        std::string(Config.backend_host.begin(), Config.backend_host.end()),
        Config.backend_port);
}

void Plugin::Unload()
{
    ArkApi::GetCommands().RemoveChatCommand("/u");
    ArkApi::GetCommands().RemoveChatCommand("/dow");
}

// ─── Carrega configuração ─────────────────────────────────────────────────
void Plugin::LoadConfig()
{
    const std::string config_path =
        ArkApi::Tools::GetCurrentDir() + "/ArkApi/Plugins/ArklandPlayer/ArklandPlayer.json";

    std::ifstream f(config_path);
    if (!f.is_open())
    {
        Log::GetLog()->warn("[ArklandPlayer] Config não encontrada em {}. Usando padrões.", config_path);
        return;
    }

    try
    {
        json j;
        f >> j;

        if (j.contains("BackendHost"))
        {
            std::string host = j["BackendHost"].get<std::string>();
            Config.backend_host = std::wstring(host.begin(), host.end());
        }
        if (j.contains("BackendPort"))   Config.backend_port   = j["BackendPort"].get<int>();
        if (j.contains("BackendPath"))
        {
            std::string path = j["BackendPath"].get<std::string>();
            Config.backend_path = std::wstring(path.begin(), path.end());
        }
        if (j.contains("ServerApiKey"))  Config.server_api_key = j["ServerApiKey"].get<std::string>();
        if (j.contains("ServerName"))    Config.server_name    = j["ServerName"].get<std::string>();
        if (j.contains("MapName"))       Config.map_name       = j["MapName"].get<std::string>();
        if (j.contains("AllowedGroups")) Config.allowed_groups = j["AllowedGroups"].get<std::vector<std::string>>();
    }
    catch (const std::exception& e)
    {
        Log::GetLog()->error("[ArklandPlayer] Erro ao ler config: {}", e.what());
    }
}

// ─── Utilitários ──────────────────────────────────────────────────────────
std::string Plugin::GetSteamId(AShooterPlayerController* pc)
{
    const uint64 id = ArkApi::GetApiUtils().GetSteamIdFromController(pc);
    return std::to_string(id);
}

void Plugin::SendMsg(AShooterPlayerController* pc, const FString& text)
{
    ArkApi::GetApiUtils().SendServerMessage(pc, FColorList::Green, *text);
}

bool Plugin::IsAllowed(APlayerController* player_controller)
{
    auto* pc = static_cast<AShooterPlayerController*>(player_controller);
    const FString steam_id = FString(GetSteamId(pc).c_str());

    for (const auto& group : Config.allowed_groups)
    {
        if (Permissions::IsPlayerInGroup(steam_id, FString(group.c_str())))
            return true;
    }
    return false;
}

// ─── /u — Upload de inventário ────────────────────────────────────────────
void Plugin::CommandUpload(AShooterPlayerController* pc, FString*, EChatSendMode::Type)
{
    if (!IsAllowed(pc))
    {
        SendMsg(pc, L"[ARKLAND] Você não tem permissão para usar /u.");
        return;
    }

    APrimalCharacter* character = static_cast<APrimalCharacter*>(pc->CharacterField());
    if (!character)
    {
        SendMsg(pc, L"[ARKLAND] Personagem não encontrado.");
        return;
    }

    UPrimalInventoryComponent* inventory = character->MyInventoryComponentField();
    if (!inventory)
    {
        SendMsg(pc, L"[ARKLAND] Inventário não acessível.");
        return;
    }

    const std::string steam_id = GetSteamId(pc);
    json payload;
    payload["steam_id"]    = steam_id;
    payload["server_name"] = Config.server_name;
    payload["map_name"]    = Config.map_name;
    payload["items"]       = json::array();

    // Itera os itens do inventário
    TArray<UPrimalItem*>& items = inventory->InventoryItemsField();
    for (int i = 0; i < items.Num(); ++i)
    {
        UPrimalItem* item = items[i];
        if (!item) continue;

        json item_json;

        // Blueprint path (ex: Blueprint'/Game/.../PrimalItemArmor_MetalHelmet.PrimalItemArmor_MetalHelmet')
        FString bp;
        item->GetFullName(&bp, nullptr);
        item_json["blueprint_path"] = bp.ToString();

        item_json["quantity"]    = static_cast<int>(item->ItemQuantityField());
        item_json["quality"]     = static_cast<float>(item->ItemRatingField());
        item_json["durability"]  = static_cast<float>(item->SavedDurabilityField());
        item_json["is_equipped"] = item->bIsEquippedField();
        item_json["slot_index"]  = i;

        // Nome customizado (se o jogador renomeou o item)
        FString custom_name = item->CustomItemNameField();
        if (!custom_name.IsEmpty())
            item_json["custom_name"] = custom_name.ToString();

        payload["items"].push_back(item_json);
    }

    SendMsg(pc, L"[ARKLAND] Enviando inventário para a nuvem...");

    // POST /inventory/upload
    const std::wstring path = Config.backend_path + L"/inventory/upload";
    auto response = HttpClient::Post(
        Config.backend_host, Config.backend_port, path,
        payload.dump(),
        {{L"X-Server-Key", std::wstring(Config.server_api_key.begin(), Config.server_api_key.end())}}
    );

    if (response.success)
    {
        int count = static_cast<int>(items.Num());
        FString msg = FString::Format(L"[ARKLAND] Inventário salvo na nuvem! ({0} itens)", count);
        SendMsg(pc, msg);
    }
    else if (response.status_code == 404)
    {
        SendMsg(pc, L"[ARKLAND] Jogador não encontrado. Faça login no app ARKLAND Player primeiro.");
    }
    else if (response.status_code == 403)
    {
        SendMsg(pc, L"[ARKLAND] Sem permissão para usar /u.");
    }
    else
    {
        SendMsg(pc, L"[ARKLAND] Falha ao salvar inventário. Tente novamente.");
        Log::GetLog()->error("[ArklandPlayer] /u falhou: {} | {}", response.status_code, response.body);
    }
}

// ─── /dow — Download de inventário ───────────────────────────────────────
void Plugin::CommandDownload(AShooterPlayerController* pc, FString*, EChatSendMode::Type)
{
    if (!IsAllowed(pc))
    {
        SendMsg(pc, L"[ARKLAND] Você não tem permissão para usar /dow.");
        return;
    }

    APrimalCharacter* character = static_cast<APrimalCharacter*>(pc->CharacterField());
    if (!character)
    {
        SendMsg(pc, L"[ARKLAND] Personagem não encontrado.");
        return;
    }

    UPrimalInventoryComponent* inventory = character->MyInventoryComponentField();
    if (!inventory)
    {
        SendMsg(pc, L"[ARKLAND] Inventário não acessível.");
        return;
    }

    const std::string steam_id = GetSteamId(pc);
    SendMsg(pc, L"[ARKLAND] Baixando inventário da nuvem...");

    // GET /inventory/download/{steam_id}
    const std::wstring path = Config.backend_path + L"/inventory/download/" +
        std::wstring(steam_id.begin(), steam_id.end());

    auto response = HttpClient::Get(
        Config.backend_host, Config.backend_port, path,
        {{L"X-Server-Key", std::wstring(Config.server_api_key.begin(), Config.server_api_key.end())}}
    );

    if (!response.success)
    {
        if (response.status_code == 404)
            SendMsg(pc, L"[ARKLAND] Nenhum inventário salvo encontrado.");
        else if (response.status_code == 403)
            SendMsg(pc, L"[ARKLAND] Sem permissão para usar /dow.");
        else
        {
            SendMsg(pc, L"[ARKLAND] Falha ao baixar inventário.");
            Log::GetLog()->error("[ArklandPlayer] /dow falhou: {} | {}", response.status_code, response.body);
        }
        return;
    }

    json items_json;
    try { items_json = json::parse(response.body); }
    catch (...) { SendMsg(pc, L"[ARKLAND] Resposta inválida do servidor."); return; }

    // Limpa inventário atual (apenas itens não equipados)
    TArray<UPrimalItem*>& current_items = inventory->InventoryItemsField();
    TArray<UPrimalItem*> to_remove;
    for (int i = 0; i < current_items.Num(); ++i)
    {
        UPrimalItem* item = current_items[i];
        if (item && !item->bIsEquippedField())
            to_remove.Add(item);
    }
    for (UPrimalItem* item : to_remove)
        inventory->RemoveItem(&item->ItemIdField(), false, false, true, true);

    // Adiciona itens do snapshot
    int added = 0;
    for (const auto& item_json : items_json)
    {
        try
        {
            FString bp(item_json["blueprint_path"].get<std::string>().c_str());
            UClass* item_class = UClass::TryFindObject<UClass>(bp, false);
            if (!item_class) continue;

            UPrimalItem* new_item = UPrimalItem::StaticClass()->CreateDefaultObject<UPrimalItem>();
            if (!new_item) continue;

            new_item->ItemQuantityField() = item_json.value("quantity", 1);
            new_item->ItemRatingField()   = item_json.value("quality", 0.0f);
            new_item->SavedDurabilityField() = item_json.value("durability", 0.0f);

            std::string custom_name = item_json.value("custom_name", "");
            if (!custom_name.empty())
                new_item->CustomItemNameField() = FString(custom_name.c_str());

            inventory->AddItem(&new_item, false);
            ++added;
        }
        catch (...) { /* item inválido, pula */ }
    }

    FString msg = FString::Format(L"[ARKLAND] Inventário restaurado! ({0} itens)", added);
    SendMsg(pc, msg);
}
