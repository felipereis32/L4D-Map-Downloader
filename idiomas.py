import gettext
from pathlib import Path

PASTA_LOCALES = Path(__file__).resolve().parent / "locales"
DOMINIO = "messages"

IDIOMAS_DISPONIVEIS = {
    "1": ("pt_BR", "Português (Brasil)"),
    "2": ("en", "English"),
}

_traducao = gettext.NullTranslations()
_idioma_atual = "pt_BR"


def definir_idioma(codigo):
    """Carrega o catálogo de tradução do idioma escolhido."""
    global _traducao, _idioma_atual

    idiomas_validos = {
        codigo_idioma
        for codigo_idioma, _nome in IDIOMAS_DISPONIVEIS.values()
    }

    if codigo not in idiomas_validos:
        codigo = "pt_BR"

    try:
        traducao = gettext.translation(
            DOMINIO,
            localedir=str(PASTA_LOCALES),
            languages=[codigo],
        )

        _traducao = traducao
        _idioma_atual = codigo

    except OSError:
        if codigo != "pt_BR":
            try:
                _traducao = gettext.translation(
                    DOMINIO,
                    localedir=str(PASTA_LOCALES),
                    languages=["pt_BR"],
                )
                _idioma_atual = "pt_BR"

            except OSError:
                _traducao = gettext.NullTranslations()
                _idioma_atual = "pt_BR"
        else:
            _traducao = gettext.NullTranslations()
            _idioma_atual = "pt_BR"

    return _idioma_atual


def _(mensagem):
    """Traduz uma mensagem usando o idioma atualmente selecionado."""
    return _traducao.gettext(mensagem)


def obter_idioma():
    """Retorna o código do idioma atualmente selecionado."""
    return _idioma_atual


def escolher_idioma():
    """Exibe as opções e altera o idioma, se a escolha for válida."""
    print("\n" + _("Escolha o idioma:"))

    for numero, (_codigo, nome) in IDIOMAS_DISPONIVEIS.items():
        print(f"{numero}. {nome}")

    print(f"0. {_('Cancelar')}")

    opcao = input(_("Opção: ")).strip()

    if opcao == "0":
        return _idioma_atual

    if opcao not in IDIOMAS_DISPONIVEIS:
        print(_("Opção inválida."))
        return _idioma_atual

    codigo, nome = IDIOMAS_DISPONIVEIS[opcao]
    idioma_carregado = definir_idioma(codigo)

    if idioma_carregado != codigo:
        print(_("Não foi possível carregar o idioma escolhido."))
        return idioma_carregado

    print(_("Idioma selecionado: ") + nome)

    return _idioma_atual

definir_idioma("pt_BR")
