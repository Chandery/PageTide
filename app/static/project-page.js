/* Project settings: rename and delete. Talks to /api/projects only; it never calls the AI. */
'use strict';
const $ = (s) => document.querySelector(s);
const part = (role) => $(`[data-role="${role}"]`);
const projectId = new URLSearchParams(location.search).get('project_id') || localStorage.getItem('pdh-current-project') || '';
const state = {project: null, busy: false};
const policyEditor = PaperPolicy.mount(part('paperPolicy'));

function notice(message, isError = true) {
  const el = part('notice');
  el.hidden = !message; el.textContent = message || ''; el.classList.toggle('error', isError);
}

async function call(path, options) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

/* The delete button works only when the typed text is exactly the project's name. */
function matches(typed, name) { return !!name && String(typed) === String(name); }

function render() {
  const project = state.project;
  part('main').hidden = !project;
  if (!project) return;
  part('back').href = `/?project_id=${encodeURIComponent(project.id)}`;
  part('routeLink').href = `/route.html?project_id=${encodeURIComponent(project.id)}`;
  part('name').value = project.name;
  part('nameEcho').textContent = project.name;
  const modes = {quick: '快速创建', manual: '手动创建', ai_guided: 'AI 引导创建'};
  const facts = [['创建方式', modes[project.creation_mode] || project.creation_mode, !modes[project.creation_mode]],
                 ['关键词', (project.keywords || []).join('、') || '（还没有）', Boolean(project.keywords?.length)]];
  const list = part('facts');
  list.replaceChildren();
  facts.forEach(([key, value, userData]) => {
    const dt = document.createElement('dt'), dd = document.createElement('dd');
    dt.textContent = key; dd.textContent = value; if(userData)dd.setAttribute('data-no-i18n', '');
    list.append(dt, dd);
  });
  part('delete').disabled = !matches(part('confirm').value, project.name) || state.busy;
}

part('confirm').oninput = render;
part('languageForm').onsubmit = async event => {
  event.preventDefault();
  if (state.busy) return;
  let value;
  try {value=policyEditor.read();} catch(error) {notice(error.message); return;}
  state.busy=true; policyEditor.disabled(true); part('languageSave').disabled=true;
  try {
    const out=await call(`/api/projects/${encodeURIComponent(projectId)}`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'language',...value})});
    state.project=out.project; policyEditor.set(out.project.language_policy); notice('论文语言已保存，下次生成推荐时使用。',false);
  } catch(error) {notice(error.message);}
  finally {state.busy=false; policyEditor.disabled(false); part('languageSave').disabled=false; render();}
};
part('renameForm').onsubmit = async (event) => {
  event.preventDefault();
  if (state.busy) return;
  const name = part('name').value.trim();
  if (!name) { notice('项目名称不能为空。'); return; }
  state.busy = true; part('rename').disabled = true;
  try {
    const out = await call(`/api/projects/${encodeURIComponent(projectId)}`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action: 'rename', name})});
    state.project = out.project; part('confirm').value = '';
    notice('名称已保存。', false);
  } catch (error) { notice(error.message); }
  finally { state.busy = false; part('rename').disabled = false; render(); }
};
part('delete').onclick = async () => {
  if (state.busy || !matches(part('confirm').value, state.project && state.project.name)) return;
  state.busy = true; part('delete').disabled = true;
  try {
    const out = await call(`/api/projects/${encodeURIComponent(projectId)}`, {method: 'DELETE'});
    if (localStorage.getItem('pdh-current-project') === projectId) localStorage.removeItem('pdh-current-project');
    sessionStorage.setItem('pdh-notice', `已删除项目“${out.name}”。数据库备份：${out.backup}`);
    location.href = '/';
  } catch (error) { notice(error.message); state.busy = false; render(); }
};

(async () => {
  if (!projectId) { notice('没有指定项目。请从今日推荐页进入。'); return; }
  try {
    const projects = (await call('/api/projects')).projects || [];
    state.project = projects.find((p) => p.id === projectId) || null;
    if (state.project) policyEditor.set(state.project.language_policy);
    if (!state.project) notice('找不到这个项目，它可能已经被删除。');
  } catch (error) { notice(error.message); }
  render();
})();
if (typeof module === 'object' && module.exports) module.exports = {matches};
