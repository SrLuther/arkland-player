#pragma once
// ============================================================
//  HttpClient.h — Cliente HTTP síncrono via WinHTTP
//  Usado pelo plugin ArklandPlayer para comunicar com o backend
// ============================================================
#include <string>
#include <map>
#include <stdexcept>
#include <windows.h>
#include <winhttp.h>

#pragma comment(lib, "winhttp.lib")

struct HttpResponse
{
    int  status_code = 0;
    std::string body;
    bool success = false;
};

class HttpClient
{
public:
    static HttpResponse Post(
        const std::wstring& host, int port, const std::wstring& path,
        const std::string& body,
        const std::map<std::wstring, std::wstring>& headers = {})
    {
        return Request(L"POST", host, port, path, body, headers);
    }

    static HttpResponse Get(
        const std::wstring& host, int port, const std::wstring& path,
        const std::map<std::wstring, std::wstring>& headers = {})
    {
        return Request(L"GET", host, port, path, "", headers);
    }

private:
    static HttpResponse Request(
        const std::wstring& method,
        const std::wstring& host,
        int port,
        const std::wstring& path,
        const std::string& body,
        const std::map<std::wstring, std::wstring>& extra_headers)
    {
        HttpResponse result;

        HINTERNET hSession = WinHttpOpen(
            L"ArklandPlayer/1.0",
            WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
            WINHTTP_NO_PROXY_NAME,
            WINHTTP_NO_PROXY_BYPASS, 0);
        if (!hSession) return result;

        HINTERNET hConnect = WinHttpConnect(hSession, host.c_str(), static_cast<INTERNET_PORT>(port), 0);
        if (!hConnect) { WinHttpCloseHandle(hSession); return result; }

        DWORD flags = (port == 443) ? WINHTTP_FLAG_SECURE : 0;
        HINTERNET hRequest = WinHttpOpenRequest(
            hConnect, method.c_str(), path.c_str(),
            nullptr, WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, flags);
        if (!hRequest) {
            WinHttpCloseHandle(hConnect);
            WinHttpCloseHandle(hSession);
            return result;
        }

        // Cabeçalhos padrão
        WinHttpAddRequestHeaders(hRequest,
            L"Content-Type: application/json\r\n",
            static_cast<DWORD>(-1L), WINHTTP_ADDREQ_FLAG_ADD);

        // Cabeçalhos extras (ex: X-Server-Key)
        for (const auto& kv : extra_headers) {
            std::wstring header_line = kv.first + L": " + kv.second + L"\r\n";
            WinHttpAddRequestHeaders(hRequest, header_line.c_str(),
                static_cast<DWORD>(-1L), WINHTTP_ADDREQ_FLAG_ADD);
        }

        BOOL sent = WinHttpSendRequest(
            hRequest,
            WINHTTP_NO_ADDITIONAL_HEADERS, 0,
            body.empty() ? nullptr : const_cast<char*>(body.c_str()),
            static_cast<DWORD>(body.size()),
            static_cast<DWORD>(body.size()), 0);

        if (!sent || !WinHttpReceiveResponse(hRequest, nullptr)) {
            WinHttpCloseHandle(hRequest);
            WinHttpCloseHandle(hConnect);
            WinHttpCloseHandle(hSession);
            return result;
        }

        // Status HTTP
        DWORD statusCode = 0;
        DWORD statusSize = sizeof(statusCode);
        WinHttpQueryHeaders(hRequest,
            WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
            WINHTTP_HEADER_NAME_BY_INDEX, &statusCode, &statusSize, WINHTTP_NO_HEADER_INDEX);
        result.status_code = static_cast<int>(statusCode);

        // Lê corpo da resposta
        DWORD bytesAvailable = 0;
        while (WinHttpQueryDataAvailable(hRequest, &bytesAvailable) && bytesAvailable > 0) {
            std::string chunk(bytesAvailable, '\0');
            DWORD bytesRead = 0;
            WinHttpReadData(hRequest, &chunk[0], bytesAvailable, &bytesRead);
            chunk.resize(bytesRead);
            result.body += chunk;
        }

        result.success = (result.status_code >= 200 && result.status_code < 300);

        WinHttpCloseHandle(hRequest);
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        return result;
    }
};
