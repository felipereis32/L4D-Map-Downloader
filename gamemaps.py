import re
import unicodedata
import msvcrt
from difflib import SequenceMatcher
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
import requests
from idiomas import _

BASE_URL = "https://www.gamemaps.com"
LIST_URL = f"{BASE_URL}/l4d/campaign"
TIMEOUT = 20
MAX_PAGINAS = 500
TENTATIVAS = 3

CAMPANHAS_CONHECIDAS = {
    f"{BASE_URL}/details/4075": "Dead Vacation (L4D1)",
    f"{BASE_URL}/details/36481": "The Evil Within (L4D1 Port)",
    f"{BASE_URL}/details/2406": "City 17",
    f"{BASE_URL}/details/2661": "Dead Before Dawn",
    f"{BASE_URL}/details/36119": "Yama (L4D1 Port)",
}


TERMOS_EXCLUIDOS = (
    "versus",
    "nav fix",
    "tank music",
    "soundtrack",
    "weapon skin",
    "weapon mod",
    "menu mod",
    "hud",
    "spray",
    "wallpaper",
    "background",
    "model replacement",
)


class PesquisaCancelada(Exception):
    """Indica que o usuário solicitou o cancelamento da busca."""


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.link = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "a" and attrs.get("href"):
            self.link = [attrs["href"], []]

    def handle_data(self, data):
        if self.link is not None:
            self.link[1].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.link is not None:
            href, partes = self.link
            nome = " ".join(" ".join(partes).split())

            self.links.append((href, nome))
            self.link = None


def cancelar_solicitado():
    """
    Verifica se o usuário pressionou 0 durante a pesquisa.

    No Windows, pressione apenas a tecla 0, sem Enter.
    """
    while msvcrt.kbhit():
        tecla = msvcrt.getwch()

        if tecla == "0":
            return True

    return False


def criar_sessao():
    sessao = requests.Session()

    sessao.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    })

    return sessao


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto).casefold())

    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )

    return " ".join(
        re.sub(r"[^a-z0-9]+", " ", texto).split()
    )


def url_detalhes(url):
    endereco = urlparse(urljoin(BASE_URL + "/", url))

    if endereco.netloc.lower() not in (
        "gamemaps.com",
        "www.gamemaps.com",
    ):
        return None

    if not re.fullmatch(r"/details/\d+/?", endereco.path):
        return None

    return f"{BASE_URL}{endereco.path.rstrip('/')}"


def nome_excluido(nome):
    titulo = normalizar(nome)

    return any(
        normalizar(termo) in titulo
        for termo in TERMOS_EXCLUIDOS
    )


def corresponde_pesquisa(termo, nome):
    termo = normalizar(termo)
    nome = normalizar(nome)

    if not termo or not nome:
        return False

    if termo in nome:
        return True

    palavras_termo = termo.split()
    palavras_nome = nome.split()

    for palavra in palavras_termo:
        if palavra in palavras_nome:
            continue

        if len(palavra) <= 3:
            return False

        if not any(
            SequenceMatcher(None, palavra, outra).ratio() >= 0.82
            for outra in palavras_nome
        ):
            return False

    return True


def adicionar_resultado(resultados, url, nome):
    endereco = url_detalhes(url)

    if not endereco or not nome:
        return

    if endereco in CAMPANHAS_CONHECIDAS:
        nome = CAMPANHAS_CONHECIDAS[endereco]
    elif nome_excluido(nome):
        return

    resultados[endereco] = {
        "nome": nome,
        "url": endereco,
        "tipo": _("Campanha"),
    }


def ler_pagina(sessao, numero):
    url = f"{LIST_URL}?page={numero}"
    ultimo_erro = None

    for _ in range(TENTATIVAS):
        if cancelar_solicitado():
            raise PesquisaCancelada

        try:
            resposta = sessao.get(url, timeout=TIMEOUT)
            resposta.raise_for_status()

            parser = PageParser()
            parser.feed(resposta.text)
            parser.close()

            return parser

        except requests.RequestException as erro:
            ultimo_erro = erro

            if cancelar_solicitado():
                raise PesquisaCancelada

    raise ultimo_erro


def buscar_mapas(termo, paginas=None):
    termo = termo.strip()

    if not termo:
        return []

    resultados = {}
    urls_processadas = set()
    paginas_repetidas = set()
    falhas_consecutivas = 0
    cancelada = False

    for url, nome in CAMPANHAS_CONHECIDAS.items():
        if corresponde_pesquisa(termo, nome):
            adicionar_resultado(resultados, url, nome)

    limite = MAX_PAGINAS

    if (
        isinstance(paginas, int)
        and not isinstance(paginas, bool)
        and paginas > 0
    ):
        limite = min(paginas, MAX_PAGINAS)

    print(
        "\n" + _("Pressione 0 (sem Enter) para cancelar a pesquisa.")
    )

    try:
        with criar_sessao() as sessao:
            for numero in range(1, limite + 1):
                if cancelar_solicitado():
                    cancelada = True
                    break

                try:
                    parser = ler_pagina(sessao, numero)
                    falhas_consecutivas = 0

                except PesquisaCancelada:
                    cancelada = True
                    break

                except requests.RequestException as erro:
                    falhas_consecutivas += 1

                    print(
                        "\n" + _(
                            "[AVISO] Falha na página {numero}: {erro}"
                        ).format(numero=numero, erro=erro)
                    )

                    if cancelar_solicitado():
                        cancelada = True
                        break

                    if falhas_consecutivas >= 3:
                        print(
                            _(
                                "[PARADA] Três páginas consecutivas "
                                "falharam."
                            )
                        )
                        break

                    continue

                if cancelar_solicitado():
                    cancelada = True
                    break

                links_validos = []

                for href, nome in parser.links:
                    endereco = url_detalhes(
                        urljoin(BASE_URL + "/", href)
                    )

                    if endereco:
                        links_validos.append((endereco, nome))

                if not links_validos:
                    print(
                        "\n" + _(
                            "[FIM] A listagem terminou na página "
                            "{numero}."
                        ).format(numero=numero)
                    )
                    break

                assinatura = tuple(
                    sorted({
                        url
                        for url, _ in links_validos
                    })
                )

                if assinatura in paginas_repetidas:
                    print(
                        "\n" + _(
                            "[FIM] Conteúdo repetido na página "
                            "{numero}."
                        ).format(numero=numero)
                    )
                    break

                paginas_repetidas.add(assinatura)

                for endereco, nome in links_validos:
                    if endereco in urls_processadas or not nome:
                        continue

                    urls_processadas.add(endereco)

                    if corresponde_pesquisa(termo, nome):
                        adicionar_resultado(
                            resultados,
                            endereco,
                            nome,
                        )

                mensagem = _(
                    "\rPesquisando: página {numero} | "
                    "{quantidade} resultado(s)..."
                ).format(
                    numero=numero,
                    quantidade=len(resultados),
                )

                print(mensagem, end="", flush=True)

    except KeyboardInterrupt:
        cancelada = True

    print()

    if cancelada:
        print(
            _("[CANCELADO] Pesquisa interrompida pelo usuário.")
        )
    elif limite == MAX_PAGINAS:
        print(
            _("[INFO] Limite de segurança: {limite} páginas.").format(
                limite=MAX_PAGINAS
            )
        )

    return sorted(
        resultados.values(),
        key=lambda mapa: mapa["nome"].casefold(),
    )


def verificar_conexao():
    try:
        with criar_sessao() as sessao:
            resposta = sessao.get(BASE_URL, timeout=TIMEOUT)
            resposta.raise_for_status()

            return True

    except requests.RequestException as erro:
        print(
            _("[ERRO] Falha de conexão com o GameMaps: {erro}").format(
                erro=erro
            )
        )
        return False


def obter_link_download(url_campanha):
    endereco = url_detalhes(url_campanha)

    if not endereco:
        print(_(" [ERRO] URL de campanha inválida."))
        return None

    campanha_id = (
        urlparse(endereco).path.rstrip("/").split("/")[-1]
    )

    try:
        with criar_sessao() as sessao:
            pagina = sessao.get(endereco, timeout=TIMEOUT)
            pagina.raise_for_status()

            sessao.headers.update({
                "Referer": endereco,
                "Origin": BASE_URL,
            })

            resposta = sessao.post(
                f"{BASE_URL}/downloads/download",
                data=[
                    ("ids[]", campanha_id),
                    ("noqueue", "true"),
                    ("direct", "true"),
                ],
                timeout=TIMEOUT,
                allow_redirects=False,
            )

            if resposta.status_code in (301, 302, 303, 307, 308):
                destino = resposta.headers.get("Location")

                if destino:
                    return urljoin(BASE_URL + "/", destino)

            print(
                _(
                    "[ERRO] Redirecionamento de download não recebido. "
                    "Status HTTP: {status}"
                ).format(status=resposta.status_code)
            )

            return None

    except requests.RequestException as erro:
        print(
            _("[ERRO] Falha ao obter o link: {erro}").format(
                erro=erro
            )
        )
        return None
