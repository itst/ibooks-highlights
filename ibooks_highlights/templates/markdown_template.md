# [{{title}}](x-devonthink-item://) [🕵️‍♀️](x-devonthink://search?query={{title_encoded}})
[{{author}}](x-devonthink://search?query={{author_encoded}})

## My notes <a name="my_notes_dont_delete"></a>

{{ reader_notes }}

## iBooks notes <a name="ibooks_notes_dont_delete"></a>
{% set vars={'last': none} %}
{% for h in highlights %}
{# found a new chapter, print its title #}
{% if h.selected_text %}
{% if h.chapter is not none and vars.last != h.chapter %}
{# stupid hacky nonsense to get around assignment not holding in outer scope #}
{% if vars.update({'last': h.chapter}) %}{% endif %}

### {{ h.chapter }}
{% endif %}

{# print the quote #}
{{ h.selected_text }}{% if h.note is not none and h.note|length > 0 %}  _NOTE: {{ h.note }}_{% endif %}

{% endif %}
{% endfor %}
