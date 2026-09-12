const resources = [];
const search = document.querySelector('#search');
const category = document.querySelector('#category');
const tag = document.querySelector('#tag');
const count = document.querySelector('#result-count');
const parameters = new URLSearchParams(window.location.search);
search.value = parameters.get('q') || '';
category.value = parameters.get('category') || '';
tag.value = parameters.get('tag') || '';
function applyFilters() {
  const query = search.value.trim().toLowerCase();
  let visible = 0;
  for (const resource of resources) {
    const searchable = [resource.name, resource.description, resource.category, ...resource.tags].join(' ').toLowerCase();
    const matches = (!query || searchable.includes(query)) && (!category.value || resource.category === category.value) && (!tag.value || resource.tags.includes(tag.value));
    document.querySelector(`[data-resource-id="${resource.id}"]`).hidden = !matches;
    if (matches) visible += 1;
  }
  count.textContent = `${visible} resource${visible === 1 ? '' : 's'} shown`;
}
for (const control of [search, category, tag]) {
  control.addEventListener('input', applyFilters);
  control.addEventListener('change', applyFilters);
}
applyFilters();
