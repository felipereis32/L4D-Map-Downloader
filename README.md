# L4D Map Downloader

Aplicativo desktop desenvolvido em Python e PySide6 para pesquisar, baixar e instalar campanhas personalizadas para **Left 4 Dead 1** a partir do site GameMaps.

O projeto reúne uma interface gráfica, pesquisa de campanhas, gerenciamento de downloads, detecção da instalação do jogo e suporte a múltiplos idiomas.

## Funcionalidades

- Pesquisa de campanhas personalizadas disponíveis no GameMaps.
- Download e instalação de campanhas.
- Gerenciamento de downloads simultâneos.
- Acompanhamento do progresso dos downloads.
- Detecção da instalação do Left 4 Dead 1 pela Steam.
- Seleção manual da pasta do jogo quando a detecção automática não funciona.
- Interface gráfica desenvolvida com PySide6.
- Temas claro e escuro.
- Configurações persistentes, incluindo idioma, tema, pasta do jogo e limite de downloads simultâneos.
- Suporte a oito idiomas.

## Idiomas disponíveis

- 🇧🇷 Português (Brasil)
- 🇺🇸 Inglês
- 🇪🇸 Espanhol
- 🇫🇷 Francês
- 🇮🇹 Italiano
- 🇩🇪 Alemão
- 🇷🇺 Russo
- 🇨🇳 Chinês simplificado

## Requisitos

- Windows.
- Left 4 Dead 1 instalado para utilizar os recursos de detecção e instalação do jogo.
- Python 3.10 ou superior para executar o código-fonte.
- WinRAR instalado para as operações de extração que dependem dele.
- Conexão com a internet para pesquisar e baixar campanhas.

## Executar o código-fonte

1. Baixe ou clone este repositório.
2. Abra um terminal na pasta do projeto.
3. Instale as dependências:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Execute o aplicativo:

   ```bash
   python main.py
   ```

Na primeira execução, o aplicativo cria seu arquivo de configuração, caso ele ainda não exista.

## Estrutura do projeto

```text
L4D Map Downloader/
├── main.py
├── downloader.py
├── game_detector.py
├── gamemaps.py
├── idiomas.py
├── locales/
├── l4d1logo.jpg
├── L4dBanner.png
├── requirements.txt
└── README.md
```

- `main.py`: interface gráfica e integração dos recursos.
- `downloader.py`: downloads, gerenciamento de tarefas e instalação.
- `game_detector.py`: detecção da instalação do jogo.
- `gamemaps.py`: pesquisa de campanhas e obtenção de links.
- `idiomas.py`: carregamento e gerenciamento das traduções.
- `locales/`: arquivos JSON dos idiomas disponíveis.

## Download para Windows

O link para download está disponivel em Releases.

## Aviso

Este é um projeto independente, sem vínculo oficial com a Valve Corporation ou com o GameMaps. As campanhas são disponibilizadas por terceiros. Respeite os direitos dos respectivos criadores e os termos dos sites utilizados.

## Desenvolvimento

O projeto utiliza Python, PySide6, Requests e VDF. Contribuições, sugestões e relatos de problemas são bem-vindos.
