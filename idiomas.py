import json
from pathlib import Path

PASTA_LOCALES = Path(__file__).resolve().parent / "locales"

IDIOMAS_DISPONIVEIS = {
    "pt_BR": "Português (Brasil)",
    "en": "English",
    "es_ES": "Español",
    "fr_FR": "Français",
    "it_IT": "Italiano",
    "de_DE": "Deutsch",
    "ru_RU": "Русский",
    "zh_CN": "简体中文",
}

IDIOMA_PADRAO = "pt_BR"

_idioma_atual = IDIOMA_PADRAO
_traducoes = {}
_traducoes_padrao = {}


def _carregar_json(codigo):
    """Carrega um arquivo JSON de tradução."""
    arquivo = PASTA_LOCALES / f"{codigo}.json"

    with arquivo.open("r", encoding="utf-8") as f:
        dados = json.load(f)

    if not isinstance(dados, dict):
        raise ValueError(
            f"O arquivo de idioma {arquivo.name} "
            "precisa conter um objeto JSON."
        )

    return {
        chave: valor
        for chave, valor in dados.items()
        if isinstance(chave, str) and isinstance(valor, str)
    }


def definir_idioma(codigo):
    """
    Carrega o idioma solicitado.

    Se o idioma não existir ou estiver inválido, tenta usar
    português brasileiro. Retorna o idioma efetivamente carregado.
    """
    global _idioma_atual
    global _traducoes
    global _traducoes_padrao

    if codigo not in IDIOMAS_DISPONIVEIS:
        codigo = IDIOMA_PADRAO

    try:
        traducoes_padrao = _carregar_json(IDIOMA_PADRAO)
    except (OSError, json.JSONDecodeError, ValueError):
        traducoes_padrao = {}

    if codigo == IDIOMA_PADRAO:
        traducoes = traducoes_padrao
    else:
        try:
            traducoes = _carregar_json(codigo)
        except (OSError, json.JSONDecodeError, ValueError):
            codigo = IDIOMA_PADRAO
            traducoes = traducoes_padrao

    _idioma_atual = codigo
    _traducoes = traducoes
    _traducoes_padrao = traducoes_padrao

    return _idioma_atual


def _(chave, **valores):
    """
    Retorna a tradução de uma chave.

    Se a chave não existir no idioma escolhido, usa o português.
    Se também não existir no português, retorna a própria chave.

    Aceita parâmetros para interpolação:
    _("busca.resultados", quantidade=5)
    """
    texto = _traducoes.get(
        chave,
        _traducoes_padrao.get(chave, chave),
    )

    if valores:
        try:
            return texto.format(**valores)
        except (KeyError, ValueError):
            return texto

    return texto


def obter_idioma():
    """Retorna o código do idioma atual."""
    return _idioma_atual


def listar_idiomas():
    """Retorna os idiomas disponíveis para a interface."""
    return list(IDIOMAS_DISPONIVEIS.items())


def obter_traducoes():
    """Retorna uma cópia das traduções do idioma atual."""
    return _traducoes.copy()


def validar_traducoes(codigo):
    """
    Compara um idioma com o português e informa as chaves ausentes.

    Retorna um dicionário com o resultado da validação.
    """
    if codigo not in IDIOMAS_DISPONIVEIS:
        return {
            "valido": False,
            "erro": f"Idioma desconhecido: {codigo}",
            "faltantes": [],
        }

    try:
        padrao = _carregar_json(IDIOMA_PADRAO)
        traducoes = _carregar_json(codigo)

        faltantes = sorted(set(padrao) - set(traducoes))

        return {
            "valido": True,
            "erro": None,
            "faltantes": faltantes,
        }

    except (OSError, json.JSONDecodeError, ValueError) as erro:
        return {
            "valido": False,
            "erro": str(erro),
            "faltantes": [],
        }


def escolher_idioma():
    """Permite selecionar o idioma pelo terminal."""
    print("\n" + _("idioma.escolher"))

    codigos = list(IDIOMAS_DISPONIVEIS.items())

    for numero, (codigo, nome) in enumerate(codigos, start=1):
        print(f"{numero}. {nome} ({codigo})")

    print("0. " + _("comum.cancelar"))

    try:
        opcao = input(_("idioma.opcao") + " ").strip()
    except (EOFError, KeyboardInterrupt):
        return _idioma_atual

    if opcao == "0":
        return _idioma_atual

    try:
        indice = int(opcao) - 1
        codigo, _nome = codigos[indice]
    except (ValueError, IndexError):
        print(_("idioma.opcao_invalida"))
        return _idioma_atual

    idioma_carregado = definir_idioma(codigo)

    print(
        _("idioma.selecionado", nome=IDIOMAS_DISPONIVEIS[idioma_carregado])
    )

    return idioma_carregado


definir_idioma(IDIOMA_PADRAO)
