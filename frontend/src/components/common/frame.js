import { esc } from '../../utils/html.js';
import { roleName } from '../../constants/enums.js';

const navigation = [ ['observations','数据台账'], ['analysis','分析任务'], ['result','结果与复核'], ['reports','报表分发'] ];

export function frame(spec, user, route, content) {
  const active = route.page;
  return `<div class="shell"><header class="masthead"><a class="brand" href="#observations"><b>${esc(spec.organization)}</b><span>${esc(spec.direction)}</span></a><div class="session"><span>${esc(roleName[user.role])}</span><button id="logout" class="link-button">退出</button></div></header>
    <nav class="navigation" aria-label="模块">${navigation.map(([key,label]) => `<a href="#${key}" ${active === key ? 'aria-current="page"' : ''}>${label}</a>`).join('')}</nav>
    <main id="work" tabindex="-1">${content}</main><footer class="footer"><span>${esc(spec.title)}</span><span>显示时间采用北京时间</span></footer></div>`;
}

export function intro(title, detail, extra = '') {
  return `<header class="page-intro"><div><h1>${esc(title)}</h1><p>${esc(detail)}</p></div>${extra}</header>`;
}
