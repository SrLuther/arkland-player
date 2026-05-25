# Changelog — [ARKLAND]-Multi

Todas as mudanças notáveis deste projeto serão documentadas aqui.  
Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

---

## [1.0.17] — 2026-05-24
### Corrigido
- Label de status do login Dev sobreposto ao campo de senha (z-order/layout)
- `_login_status` oculto quando painel dev está ativo; `_dev_login_status` próprio dentro do painel dev
- Bordas das entradas Usuário/Senha sem destaque verde incorreto
- Servidor "pronto" apenas após health-check passar (evita "Sem conexão" logo após iniciar)

---

## [1.0.16] — 2026-05-24

### Corrigido
- IndentationError em `app.py` que impedia o app de iniciar após build (método `_do_update` com indentação errada)

---

## [1.0.15] — 2026-05-24

### Adicionado
- Painel dev: botão **Iniciar/Parar Servidor** inicia o backend localmente
- IP da máquina exibido no painel ao iniciar (`192.168.x.x:5000`) para outras máquinas conectarem
- Campo URL preenchido automaticamente ao iniciar o servidor
- Servidor encerrado automaticamente ao fechar o app
- Backend distribuído como `ArklandPlayer-Server.exe` junto ao instalador

---

## [1.0.14] — 2026-05-24

### Corrigido
- Auto-update agora exibe notificação de nova versão também na tela de login (não apenas pós-login)
- Banner clicável no topo da tela de login ao detectar nova versão disponível

---

## [1.0.13] — 2026-05-24

### Corrigido

- Login dev: erro de conexão com o backend agora mostra mensagem
  correta ("Sem conexão com o backend. Verifique a URL.") em vez
  de "Credenciais inválidas" — facilitando diagnóstico

---

## [1.0.12] — 2026-05-24

### Corrigido

- Credenciais dev (`DEV_USERNAME`/`DEV_PASSWORD`) removidas do `BaseSettings` —
  eram sobrescritas pelo `.env`, causando "Credenciais inválidas" mesmo com
  as credenciais corretas. Agora são constantes de módulo imutáveis.

---

## [1.0.11] — 2026-05-24

### Corrigido

- Login dev não depende mais do banco SQLite — valida diretamente contra
  as credenciais fixas do código, eliminando falha por hash desatualizado
  no `dev_data.db`

---

## [1.0.10] — 2026-05-24

### Corrigido

- Login dev: campo de URL do backend adicionado ao painel de acesso dev
- Credenciais do usuário dev (`dev` / `AKLserverDEV@`) agora são fixas
  no código — não dependem do `.env`
- Backend sincroniza automaticamente o hash da senha do dev a cada
  reinicialização, corrigindo logins que paravam de funcionar após
  mudança de configuração

---

## [1.0.9] — 2026-05-13

### Adicionado

- Token do agente gerado automaticamente (UUID) na primeira execução
- Botão **Copiar** e botão **Revogar** (gera novo UUID) na aba Remoto
- Botão **Colar meu token** no formulário de peer facilita a configuração

---

## [1.0.8] — 2026-05-13

### Alterado

- Porta padrão do agente remoto alterada de 19567 para 32440

---

## [1.0.7] — 2026-05-13

### Corrigido

- Atualização automática reescrita com PowerShell (era `.bat`)
- Corrige janela que abria e fechava instantaneamente sem instalar nada

---

## [1.0.6] — 2026-05-13

### Adicionado

- Aba Remoto exibe o IP local desta máquina e o endereço completo para configurar peers
- Campo Nome do peer agora é opcional (usa o IP como nome quando não preenchido)

---

## [1.0.5] — 2026-05-13

### Corrigido

- Compatibilidade: build migrado para Python 3.12
- Corrige erro `Failed to load Python DLL` em máquinas sem VC++ 2022 Runtime instalado

---

## [1.0.3] — 2026-05-13

### Adicionado

- Nova aba **Controle Remoto** — controle outra instância do app via rede
- Agente HTTP integrado: exponha esta máquina para controle externo (porta e token configuráveis)
- Cadastro de peers remotos com nome, IP, porta e token de autenticação
- Painel de peer com stats em tempo real, logs e botões Iniciar / Parar / Forçar Sync

---

## [1.0.2] — 2026-05-13

### Adicionado

- Erros separados por tipo com timestamp — card Erros no Dashboard agora abre janela de detalhes
- Botão "Ver detalhes" lista cada erro individualmente com hora, tipo e mensagem
- Botão "Limpar" zera o histórico de erros sem reiniciar a sincronização

---

## [1.0.1] — 2026-05-12

### Corrigido / Adicionado

- Imagem do instalador corrigida (sem distorção)
- URL de atualização embutida — não requer configuração manual
- Iniciar sincronização habilitado por padrão
- Nova opção: Iniciar o ARKLAND-Multi com o Windows
- Ícone da barra de tarefas corrigido

---

## [1.0.0] — 2026-05-12

### Adicionado

- Lançamento inicial do ARKLAND-Multi
- Sincronização bidirecional automática de pastas ARK Cluster
- Interface moderna com Dashboard, Configurações e Logs
- Controle de intervalo de sincronização (1–60 s)
- Inicialização automática e modo debug configuráveis
- Estatísticas em tempo real no Dashboard (arquivos, erros, último sync)
- Sistema de atualização automática integrado (verificação + download + instalação)
- Aba "Sobre" com histórico de versões e controle de update
- Notificação visual na sidebar quando há nova versão disponível
- Script de build (`build.bat`) com PyInstaller
- Script de instalador (`setup.iss`) para Inno Setup

---

<!-- Modelo para próximas versões:

## [X.Y.Z] — AAAA-MM-DD

### Adicionado
- ...

### Alterado
- ...

### Corrigido
- ...

### Removido
- ...
-->
