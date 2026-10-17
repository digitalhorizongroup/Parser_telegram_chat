let csrf='';
export const setCsrf=value=>{csrf=value||''};
export async function api(path,options={}){const headers={...(options.headers||{})};if(!['GET','HEAD'].includes(options.method||'GET'))headers['X-CSRF-Token']=csrf;const response=await fetch(path,{credentials:'same-origin',...options,headers});const type=response.headers.get('content-type')||'';const body=type.includes('json')?await response.json():await response.text();if(!response.ok)throw new Error(body?.error||body||`HTTP ${response.status}`);return body}
