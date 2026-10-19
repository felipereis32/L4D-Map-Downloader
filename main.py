from pathlib import Path
from game_detector import SteamGameDetector
from gamemaps import (
    buscar_mapas,
    obter_link_download,
    verificar_conexao,
)
from downloader import baixar_e_instalar
from idiomas import _, definir_idioma, escolher_idioma

APP_ID = "500"


def obter_pasta_jogo(detector):
    pasta = detector.localizar_jogo(APP_ID)

    if pasta:
        print(f"[OK] {_('Left 4 Dead 1 encontrado pela Steam.')}")
        print(f"{_('Localização: ')}{pasta}")
        return pasta

    print(
        f"\n[AVISO] "
        f"{_('Não foi possível localizar o jogo pela Steam.')}"
    )
    print(_("Informe a pasta que contém left4dead.exe."))

    while True:
        caminho = input(
            _("Caminho do jogo (ou 0 para sair): ")
        ).strip()

        if caminho == "0":
            return None

        pasta = detector.validar_pasta_manual(caminho)

        if pasta:
            print(f"[OK] {_('Executável encontrado.')}")
            print(f"{_('Localização: ')}{pasta}")
            return pasta

        print(
            f"[ERRO] "
            f"{_('Caminho inválido. Verifique se a pasta contém left4dead.exe.')}"
        )


def mostrar_addons(pasta_jogo):
    pasta_addons = (
        Path(pasta_jogo)
        / "left4dead"
        / "addons"
    )

    if not pasta_addons.is_dir():
        print(
            f"\n{_('Pasta addons não encontrada:')}\n"
            f"{pasta_addons}"
        )

        resposta = input(
            _("Deseja criá-la? (s/n): ")
        ).strip().casefold()

        if resposta not in ("s", "sim", "y", "yes"):
            return

        try:
            pasta_addons.mkdir(
                parents=True,
                exist_ok=True,
            )
        except OSError as erro:
            print(
                f"[ERRO] {_('Não foi possível criar a pasta:')} "
                f"{erro}"
            )
            return

    print(f"\n{_('Pasta addons:')} {pasta_addons}")
    print(f"\n{_('Conteúdo:')}")

    try:
        itens = sorted(
            pasta_addons.iterdir(),
            key=lambda item: item.name.casefold(),
        )
    except OSError as erro:
        print(f"[ERRO] {erro}")
        return

    if not itens:
        print(_(" (pasta vazia)"))
        return

    for item in itens:
        tipo = "[DIR]" if item.is_dir() else "[ARQ]"
        print(f"{tipo} {item.name}")


def menu_buscar_mapas(pasta_jogo):
    termo = input(
        "\n" + _("Digite o nome do mapa: ")
    ).strip()

    if not termo:
        print(_("Digite um nome para pesquisar."))
        return

    print("\n" + _("Pesquisando no GameMaps..."))

    mapas = buscar_mapas(termo)

    if not mapas:
        print(_("Nenhum resultado encontrado."))
        return

    print("\n" + _("Resultados:"))

    for indice, mapa in enumerate(mapas, start=1):
        print(f"\n{indice}. {mapa['nome']}")

        tipo = mapa.get("tipo")

        if tipo:
            print(f"   {_('Tipo:')} {tipo}")

        print(f"   {_('Página:')} {mapa['url']}")

    print(f"\n0. {_('Voltar')}")

    while True:
        escolha = input(
            "\n" + _("Digite o número do mapa que deseja baixar: ")
        ).strip()

        if escolha == "0":
            return

        if not escolha.isdigit():
            print(
                _("Opção inválida. Escolha um número da lista ou 0.")
            )
            continue

        indice = int(escolha)

        if not 1 <= indice <= len(mapas):
            print(
                _("Opção inválida. Escolha um número da lista ou 0.")
            )
            continue

        mapa = mapas[indice - 1]

        print("\n" + "=" * 40)
        print(_("Campanha selecionada:"))
        print(mapa["nome"])

        tipo = mapa.get("tipo")

        if tipo:
            print(f"{_('Tipo:')} {tipo}")

        print(f"{_('Página:')} {mapa['url']}")
        print("=" * 40)

        confirmar = input(
            "\n" + _(
                "Deseja tentar baixar e instalar esta campanha? (s/n): "
            )
        ).strip().casefold()

        if confirmar not in ("s", "sim", "y", "yes"):
            return

        print(
            "\n" + _("Localizando o link de download no GameMaps...")
        )

        link_download = obter_link_download(mapa["url"])

        if not link_download:
            print(
                "\n[ERRO] "
                + _(
                    "Não foi possível localizar automaticamente "
                    "o link direto do arquivo."
                )
            )
            print(
                _(
                    "O site pode exigir login, JavaScript ou uma etapa "
                    "intermediária. Confira a página da campanha."
                )
            )
            return

        print("[OK] " + _("Link de download localizado."))

        baixar_e_instalar(
            link_download,
            mapa["nome"],
            pasta_jogo,
            referer=mapa["url"],
        )

        return


def main():
    definir_idioma("pt_BR")

    print("=" * 40)
    print(_("L4D Map Downloader".center(40)))
    print("=" * 40)

    detector = SteamGameDetector()
    pasta_jogo = obter_pasta_jogo(detector)

    if pasta_jogo is None:
        print(
            "\n" + _("Não é possível continuar sem o jogo.")
        )
        return

    print(
        "\n" + _("Verificando conexão com o GameMaps...")
    )

    if not verificar_conexao():
        print(
            "\n[ERRO] " + _("Falha de conexão com o GameMaps.")
        )
        print(_("Encerrando o programa."))
        return

    print(
        "[OK] " + _("Conexão com o GameMaps estabelecida.")
    )

    while True:
        print("\n" + "=" * 40)
        print(_("L4D Map Downloader".center(40)))
        print("=" * 40)
        print(f"1. {_('Buscar e baixar mapas')}")
        print(f"2. {_('Mostrar conteúdo da pasta addons')}")
        print(f"3. {_('Mudar idioma')}")
        print(f"\n0. {_('Sair')}")

        opcao = input(
            "\n" + _("Opção: ")
        ).strip()

        if opcao == "1":
            menu_buscar_mapas(pasta_jogo)

        elif opcao == "2":
            mostrar_addons(pasta_jogo)

        elif opcao == "3":
            escolher_idioma()

        elif opcao == "0":
            print(_("Encerrando o programa."))
            break

        else:
            print(_("Opção inválida."))

if __name__ == "__main__":
    main()
