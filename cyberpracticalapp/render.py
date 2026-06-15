from jinja2 import Template


def render_template(content: str, variables: dict):

    if not content:
        return ''

    template = Template(content)

    return template.render(**variables)