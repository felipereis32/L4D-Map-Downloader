import re
import unicodedata
from difflib import SequenceMatcher
from html.parser import HTMLParser
from threading import Event
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
    """Indica que o utilizador solicitou o cancelamento da busca."""


class PageParser(HTMLParser):
    """Extrai links e nomes de campanhas diretamente da página de listagem do GameMaps."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self._link_atual = None
        self._href_atual = None
        self._texto_atual = []

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)

        if tag == "a":
            if self._link_atual is not None:
                self._finalizar_link()
            self._href_atual = atributos.get("href")
            self._texto_atual = []
            self._link_atual = True

    def handle_data(self, data):
        if self._link_atual:
            self._texto_atual.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._link_atual:
            self._finalizar_link()

    def _finalizar_link(self):
        if self._href_atual:
            texto = " ".join(" ".join(self._texto_atual).split())
            self.links.append({
                "href": self._href_atual,
                "nome": texto,
            })
        self._link_atual = None
        self._href_atual = None
        self._texto_atual = []

    def close(self):
        super().close()
        if self._link_atual is not None:
            self._finalizar_link()


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
        caractere for caractere in texto if not unicodedata.combining(caractere)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", texto).split())


def url_detalhes(url):
    if not url:
        return None

    endereco = urlparse(urljoin(BASE_URL + "/", str(url)))

    if endereco.scheme not in ("http", "https"):
        return None

    if endereco.netloc.lower() not in ("gamemaps.com", "www.gamemaps.com"):
        return None

    if not re.fullmatch(r"/details/\d+/?", endereco.path):
        return None

    return f"{BASE_URL}{endereco.path.rstrip('/')}"


def nome_excluido(nome):
    titulo = normalizar(nome)
    return any(normalizar(termo) in titulo for termo in TERMOS_EXCLUIDOS)


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


def _texto_limpo(valor):
    if valor is None:
        return ""
    return " ".join(str(valor).split()).strip()


def adicionar_resultado(resultados, url, nome):
    endereco = url_detalhes(url)

    if not endereco or not nome:
        return

    nome = _texto_limpo(nome)

    if endereco in CAMPANHAS_CONHECIDAS:
        nome = CAMPANHAS_CONHECIDAS[endereco]
    elif nome_excluido(nome):
        return

    resultados[endereco] = {
        "nome": nome,
        "url": endereco,
        "tipo": _("Campanha"),
    }


def _cancelamento_solicitado(cancelar):
    if cancelar is None:
        return False
    if isinstance(cancelar, Event):
        return cancelar.is_set()
    if callable(cancelar):
        try:
            return bool(cancelar())
        except Exception:
            return False
    return False


def ler_pagina(sessao, numero, cancelar=None):
    url = f"{LIST_URL}?page={numero}"
    ultimo_erro = None

    for _ in range(TENTATIVAS):
        if _cancelamento_solicitado(cancelar):
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
            if _cancelamento_solicitado(cancelar):
                raise PesquisaCancelada

    if ultimo_erro:
        raise ultimo_erro

    raise requests.RequestException(_("gamemaps.erro_ler_pagina"))


def buscar_mapas(termo, paginas=None, cancelar=None, progresso=None):
    termo = _texto_limpo(termo)
    buscar_mapas.ultima_busca_cancelada = False

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
    if isinstance(paginas, int) and not isinstance(paginas, bool) and paginas > 0:
        limite = min(paginas, MAX_PAGINAS)

    try:
        with criar_sessao() as sessao:
            for numero in range(1, limite + 1):
                if _cancelamento_solicitado(cancelar):
                    cancelada = True
                    break

                try:
                    parser = ler_pagina(sessao, numero, cancelar=cancelar)
                    falhas_consecutivas = 0
                except PesquisaCancelada:
                    cancelada = True
                    break
                except requests.RequestException:
                    falhas_consecutivas += 1
                    if progresso:
                        try:
                            progresso(numero, len(resultados))
                        except Exception:
                            pass
                    if falhas_consecutivas >= TENTATIVAS:
                        break
                    continue

                if _cancelamento_solicitado(cancelar):
                    cancelada = True
                    break

                links_validos = []
                for item in parser.links:
                    endereco = url_detalhes(item["href"])
                    nome = _texto_limpo(item["nome"])
                    if endereco and nome:
                        links_validos.append((endereco, nome))

                if not links_validos:
                    break

                assinatura = tuple(sorted({endereco for endereco, _ in links_validos}))
                if assinatura in paginas_repetidas:
                    break

                paginas_repetidas.add(assinatura)

                for endereco, nome in links_validos:
                    if endereco in urls_processadas:
                        continue

                    urls_processadas.add(endereco)

                    if corresponde_pesquisa(termo, nome):
                        adicionar_resultado(resultados, endereco, nome)

                if progresso:
                    try:
                        progresso(numero, len(resultados))
                    except Exception:
                        pass

    except KeyboardInterrupt:
        cancelada = True

    buscar_mapas.ultima_busca_cancelada = cancelada

    return sorted(
        resultados.values(),
        key=lambda campanha: campanha["nome"].casefold(),
    )


buscar_mapas.ultima_busca_cancelada = False


def verificar_conexao():
    try:
        with criar_sessao() as sessao:
            resposta = sessao.get(BASE_URL, timeout=TIMEOUT)
            resposta.raise_for_status()
            return True
    except requests.RequestException:
        return False


def obter_link_download(url_campanha):
    endereco = url_detalhes(url_campanha)
    if not endereco:
        return None

    campanha_id = urlparse(endereco).path.rstrip("/").split("/")[-1]

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

            return None
    except requests.RequestException:
        return None
