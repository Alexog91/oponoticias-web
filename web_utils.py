"""Utilidades compartidas de los generadores de HTML de OpoNoticias."""
import re

# Enlaces internos con .html (relativos ../ o de raíz). Excluye externos
# (contienen ':') y rutas de fichero (no son atributos href).
_RE_HREF_HTML = re.compile(r'href="((?:\.\./)*)([^":]*?)\.html(#[^"]*)?"')


def limpiar_hrefs(html):
    """Convierte los enlaces internos con .html a rutas limpias absolutas,
    que coinciden con la config `cleanUrls` de Vercel -> sin redirecciones 301.
    Solo toca href="..."; deja intactas las rutas de fichero en disco, el
    JSON-LD, el canonical (ya limpio) y los enlaces externos. Idempotente."""
    def _rep(m):
        path = m.group(2)
        anchor = m.group(3) or ""
        if path == "index":
            path = ""
        return f'href="/{path}{anchor}"'
    return _RE_HREF_HTML.sub(_rep, html)
