import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse
import requests
from idiomas import _

TIMEOUT = 60
TAMANHO_BLOCO = 128 * 1024
EXTENSOES_COMPACTADAS = {
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".tgz",
    ".tbz",
    ".tbz2",
    ".txz",
}


def formatar_tamanho(bytes_valor):
    valor = float(bytes_valor)

    for unidade in ("B", "KB", "MB", "GB", "TB"):
        if valor < 1024 or unidade == "TB":
            return f"{valor:.1f} {unidade}"

        valor /= 1024

    return f"{valor:.1f} TB"


def nome_seguro(nome):
    nome = unquote(str(nome or "")).replace("\\", "/")
    nome = nome.split("/")[-1]

    nome = re.sub(
        r'[<>:"/\\|?*\x00-\x1f]',
        "_",
        nome,
    ).strip(" .")

    return nome or "download"


def obter_pasta_downloads():
    pasta = Path.home() / "Downloads" / "L4D Map Downloader"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def localizar_winrar():
    candidatos = (
        Path(r"C:\Program Files\WinRAR\WinRAR.exe"),
        Path(r"C:\Program Files (x86)\WinRAR\WinRAR.exe"),
    )

    for caminho in candidatos:
        if caminho.is_file():
            return caminho

    encontrado = (
        shutil.which("WinRAR.exe")
        or shutil.which("winrar")
    )

    if encontrado:
        return Path(encontrado)

    return None


def nome_do_download(url, nome_sugerido=None):
    nome_url = nome_seguro(
        Path(unquote(urlparse(url).path)).name
    )

    extensao_url = Path(nome_url).suffix.casefold()

    if (
        extensao_url in EXTENSOES_COMPACTADAS
        or extensao_url == ".vpk"
    ):
        return nome_url

    nome = nome_seguro(nome_sugerido or "campanha")

    if Path(nome).suffix:
        return nome

    return nome + ".zip"


def baixar_arquivo(
    url,
    destino,
    nome_sugerido=None,
    referer=None,
):
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)

    nome = nome_do_download(url, nome_sugerido)
    arquivo = destino / nome

    temporario = arquivo.with_suffix(
        arquivo.suffix + ".part"
    )

    cabecalhos = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )
    }

    if referer:
        cabecalhos["Referer"] = referer

    try:
        with requests.get(
            url,
            headers=cabecalhos,
            stream=True,
            timeout=TIMEOUT,
            allow_redirects=True,
        ) as resposta:
            resposta.raise_for_status()

            content_type = resposta.headers.get(
                "Content-Type",
                "",
            ).casefold()

            if "text/html" in content_type:
                print(
                    _(
                        "[ERRO] O servidor retornou HTML, não um "
                        "arquivo de download. Talvez seja necessário "
                        "concluir uma etapa no GameMaps."
                    )
                )
                return None

            total = int(
                resposta.headers.get("Content-Length", 0) or 0
            )
            baixado = 0

            with open(temporario, "wb") as saida:
                for bloco in resposta.iter_content(
                    chunk_size=TAMANHO_BLOCO
                ):
                    if not bloco:
                        continue

                    saida.write(bloco)
                    baixado += len(bloco)

                    if total:
                        percentual = min(
                            100,
                            baixado * 100 // total,
                        )

                        mensagem = _(
                            "\rBaixando: {percentual}% "
                            "({baixado} / {total})"
                        ).format(
                            percentual=percentual,
                            baixado=formatar_tamanho(baixado),
                            total=formatar_tamanho(total),
                        )
                    else:
                        mensagem = _(
                            "\rBaixando: {baixado}"
                        ).format(
                            baixado=formatar_tamanho(baixado)
                        )

                    print(mensagem, end="", flush=True)

            print()

        if (
            not temporario.exists()
            or temporario.stat().st_size == 0
        ):
            print(_(" [ERRO] O arquivo baixado está vazio."))
            return None

        temporario.replace(arquivo)

        print(
            _("[OK] Download concluído: {arquivo}").format(
                arquivo=arquivo
            )
        )

        return arquivo

    except requests.RequestException as erro:
        print(
            _("\n[ERRO] Falha no download: {erro}").format(
                erro=erro
            )
        )
        return None

    except OSError as erro:
        print(
            _(
                "\n[ERRO] Não foi possível salvar o arquivo: "
                "{erro}"
            ).format(erro=erro)
        )
        return None

    finally:
        try:
            if temporario.exists():
                temporario.unlink()
        except OSError:
            pass


def copiar_arquivos_extraidos(origem, destino):
    """
    Copia os arquivos extraídos sem sobrescrever os existentes.

    Retorna a quantidade de arquivos copiados.
    """
    origem = Path(origem)
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)

    copiados = 0

    for item in origem.rglob("*"):
        try:
            relativo = item.relative_to(origem)
            alvo = destino / relativo

            if item.is_dir():
                alvo.mkdir(parents=True, exist_ok=True)
                continue

            if not item.is_file():
                continue

            alvo.parent.mkdir(parents=True, exist_ok=True)

            if alvo.exists():
                print(
                    _(
                        "[AVISO] Arquivo já existe; mantido sem "
                        "alteração: {alvo}"
                    ).format(alvo=alvo)
                )
                continue

            shutil.copy2(item, alvo)
            copiados += 1

        except OSError as erro:
            print(
                _(
                    "[AVISO] Não foi possível copiar "
                    "{item}: {erro}"
                ).format(item=item, erro=erro)
            )

    return copiados


def extrair_seguro(arquivo, destino, winrar=None):
    arquivo = Path(arquivo)
    destino = Path(destino)

    executavel = Path(winrar) if winrar else localizar_winrar()

    if not executavel or not executavel.is_file():
        print(
            _(
                "[ERRO] WinRAR não encontrado. Verifique se ele "
                "está em C:\\Program Files\\WinRAR\\WinRAR.exe"
            )
        )
        return False

    destino.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.TemporaryDirectory(
            prefix="l4d_extract_"
        ) as temporario:
            pasta_temporaria = Path(temporario)

            comando = [
                str(executavel),
                "x",
                "-ibck",
                "-o-",
                "-y",
                str(arquivo),
                str(pasta_temporaria) + os.sep,
            ]

            resultado = subprocess.run(
                comando,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=getattr(
                    subprocess,
                    "CREATE_NO_WINDOW",
                    0,
                ),
                timeout=600,
                check=False,
            )

            if resultado.returncode != 0:
                detalhe = (
                    resultado.stderr
                    or resultado.stdout
                    or ""
                ).strip()

                print(
                    _(
                        "[ERRO] O WinRAR não conseguiu extrair "
                        "o arquivo."
                    )
                )

                if detalhe:
                    print(detalhe)

                return False

            itens = list(pasta_temporaria.iterdir())

            if not itens:
                print(
                    _(
                        "[ERRO] O arquivo compactado não contém "
                        "arquivos extraídos."
                    )
                )
                return False

            copiados = copiar_arquivos_extraidos(
                pasta_temporaria,
                destino,
            )

            if copiados == 0:
                print(
                    _(
                        "[AVISO] Nenhum arquivo novo foi instalado. "
                        "Talvez os arquivos já existam em addons."
                    )
                )
                return False

            print(
                _(
                    "[OK] Extração concluída. "
                    "Arquivos instalados: {copiados}"
                ).format(copiados=copiados)
            )
            return True

    except subprocess.TimeoutExpired:
        print(
            _(
                "[ERRO] A extração demorou mais de 10 minutos "
                "e foi interrompida."
            )
        )
        return False

    except OSError as erro:
        print(
            _(
                "[ERRO] Falha ao extrair ou instalar: {erro}"
            ).format(erro=erro)
        )
        return False


def instalar_conteudo(arquivo, pasta_jogo):
    arquivo = Path(arquivo)

    pasta_addons = (
        Path(pasta_jogo)
        / "left4dead"
        / "addons"
    )

    pasta_addons.mkdir(parents=True, exist_ok=True)

    if arquivo.suffix.casefold() == ".vpk":
        destino = pasta_addons / nome_seguro(arquivo.name)

        if destino.exists():
            print(
                _(
                    "[AVISO] O arquivo já existe e foi preservado: "
                    "{nome}"
                ).format(nome=destino.name)
            )
            return False

        try:
            shutil.copy2(arquivo, destino)

            print(
                _("[OK] VPK instalado em: {destino}").format(
                    destino=destino
                )
            )
            return True

        except OSError as erro:
            print(
                _(
                    "[ERRO] Não foi possível instalar o VPK: "
                    "{erro}"
                ).format(erro=erro)
            )
            return False

    return extrair_seguro(arquivo, pasta_addons)


def baixar_e_instalar(
    url,
    nome,
    pasta_jogo,
    referer=None,
):
    pasta_downloads = obter_pasta_downloads()

    arquivo = baixar_arquivo(
        url,
        pasta_downloads,
        nome_sugerido=nome,
        referer=referer,
    )

    if arquivo is None:
        return False

    sucesso = instalar_conteudo(
        arquivo,
        pasta_jogo,
    )

    if sucesso:
        print(
            _("[OK] Campanha processada: {nome}").format(
                nome=nome
            )
        )
    else:
        print(
            _(
                "[AVISO] O download foi mantido em {arquivo}, "
                "mas a instalação não foi concluída."
            ).format(arquivo=arquivo)
        )

    return sucesso
