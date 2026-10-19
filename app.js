
const labels={queued:'Chờ',running:'Đang làm',completed:'Đã chạy xong',failed:'Thất bại',interrupted:'Bị gián đoạn',needs_review:'Cần bạn xem',cancelled:'Đã hủy',approved:'Bạn đã duyệt'};
function reviewText(text){try{const value=JSON.parse(text);if(typeof value.passed==='boolean'&&Array.isArray(value.issues))return (value.passed?'AI đánh giá: Đạt (chưa xác minh bên ngoài)':'AI đánh giá: Chưa đạt')+(value.issues.length?'\n'+value.issues.map(item=>'• '+item).join('\n'):'');}catch{}return text}
function el(tag,text){const n=document.createElement(tag);n.textContent=text;return n}
let sessionToken;
async function apiFetch(url, options={}){
 if(options.method==='POST'){
  if(!sessionToken){const response=await fetch('/api/session');if(!response.ok)throw Error('Không khởi tạo được phiên; hãy tải lại trang');sessionToken=(await response.json()).token}
  options={...options,headers:{...options.headers,'Content-Type':'application/json','X-CSRF-Token':sessionToken}};
 }
 return fetch(url,options);
}
async function viewFiles(id){
 document.querySelector('#dialog-title').textContent='Bộ tệp sản phẩm';
 try{const response=await apiFetch('/api/tasks/'+id+'/files');const data=await response.json();if(!response.ok)throw Error(data.error);
 const dialog=document.querySelector('#file-dialog'),list=document.querySelector('#file-list'),content=document.querySelector('#file-content');list.replaceChildren();content.textContent='';
 document.querySelector('#file-notice').textContent=(data.mode==='demo'?'MÔ PHỎNG. ':'')+'Mã chưa được chạy hoặc xác minh an toàn. Hãy đọc trước khi sử dụng. Trạng thái: '+(labels[data.status]||data.status);
 const download=document.querySelector('#download-file');download.hidden=false;
 function selectFile(index){content.textContent=data.files[index].content;download.href='/api/tasks/'+id+'/file/'+index;download.textContent='Tải '+data.files[index].path}
 data.files.forEach((file,index)=>{const button=el('button',file.path);button.onclick=()=>selectFile(index);list.append(button)});
 selectFile(0);dialog.showModal();
 }catch(e){document.querySelector('#error').textContent=e.message}
}
document.querySelector('#close-files').onclick=()=>document.querySelector('#file-dialog').close();
let pageOffset=0,refreshVersion=0;
let queuePaused=false,queueUpdating=false;
document.querySelector('#toggle-queue').onclick=async()=>{
 queueUpdating=true;document.querySelector('#toggle-queue').disabled=true;
 try{const response=await apiFetch('/api/queue',{method:'POST',body:JSON.stringify({paused:!queuePaused})});if(!response.ok)throw Error('Chưa đổi được trạng thái hàng đợi');await refresh()}
 catch(e){document.querySelector('#error').textContent=e.message}
 finally{queueUpdating=false;document.querySelector('#toggle-queue').disabled=false}
};
function duration(start,finish){if(!start)return 'Chưa bắt đầu';const seconds=Math.max(0,Math.floor(((finish?Date.parse(finish):Date.now())-Date.parse(start))/1000));return seconds<60?seconds+' giây':Math.floor(seconds/60)+' phút '+seconds%60+' giây'}
function updateDurations(){document.querySelectorAll('[data-duration]').forEach(element=>{element.textContent='Đã xong '+element.dataset.steps+' bước · '+duration(element.dataset.start,element.dataset.finish)})}
async function viewHistory(id){
 try{const response=await apiFetch('/api/tasks/'+id+'/history');const history=await response.json();if(!response.ok)throw Error(history.error);
 document.querySelector('#dialog-title').textContent='Lịch sử từng bước';document.querySelector('#download-file').hidden=true;
 const list=document.querySelector('#file-list'),content=document.querySelector('#file-content');list.replaceChildren();
 document.querySelector('#file-notice').textContent='Lưu kết quả từng lượt, kể cả trước khi sửa. Tổng thời gian: '+(history.timing?duration(history.timing.started_at,history.timing.finished_at):'Chưa có dữ liệu');
 const names={plan:'Điều phối',result:'Thực hiện',review:'Kiểm tra'},states={completed:'Xong',running:'Đang chạy',cancelled:'Đã hủy',failed:'Lỗi',interrupted:'Gián đoạn'};
 function describe(step){return names[step.role]+' · lượt '+step.attempt+' · '+(states[step.status]||step.status)+' · '+duration(step.started_at,step.finished_at)+'\n\n'+(step.output?(step.role==='review'?reviewText(step.output):step.output):'Chưa có kết quả cho bước này.')}
 for(const step of history.steps){const button=el('button',(names[step.role]||step.role)+' '+step.attempt+' · '+(states[step.status]||step.status));button.onclick=()=>{content.textContent=describe(step)};list.append(button)}
 content.textContent=history.steps.length?describe(history.steps[history.steps.length-1]):'Chưa có lịch sử từng bước. Nhiệm vụ tạo ở bản cũ vẫn giữ kết quả cuối.';
 document.querySelector('#file-dialog').showModal();
 }catch(e){document.querySelector('#error').textContent=e.message}
}

async function checkHealth(){const button=document.querySelector('#check-health');button.disabled=true;const status=document.querySelector('#health-status');status.textContent='Đang kiểm tra...';try{const response=await apiFetch('/api/health');if(!response.ok)throw Error('Không đọc được kết nối');const data=await response.json(),info=data.ollama;status.textContent=info.status==='ready'?'Ollama đang phản hồi · Đã có '+info.model:info.status==='model_missing'?'Ollama đang chạy, nhưng chưa tìm thấy '+info.model+'. Hãy tải mô hình trong Ollama.':'Chưa kết nối được Ollama. Hãy mở ứng dụng Ollama rồi kiểm tra lại.'}catch(e){status.textContent=e.message}finally{button.disabled=false}}
document.querySelector('#check-health').onclick=checkHealth;
document.querySelector('#backup').onclick=async()=>{if(!confirm('Tải toàn bộ lịch sử, sản phẩm và bộ nhớ về máy? Bản sao có thể chứa thông tin riêng tư.'))return;const button=document.querySelector('#backup'),status=document.querySelector('#backup-status');button.disabled=true;status.textContent='Đang tạo bản sao nhất quán...';try{const response=await apiFetch('/api/backup',{method:'POST'});if(!response.ok)throw Error('Chưa tạo được bản sao lưu');const blob=await response.blob(),url=URL.createObjectURL(blob),link=el('a','');link.href=url;link.download='bao-mat-backup-'+new Date().toISOString().replace(/[:.]/g,'-')+'.zip';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);status.textContent='Đã gửi bản sao lưu tới trình duyệt. Hãy kiểm tra thư mục tải xuống.'}catch(e){status.textContent=e.message}finally{button.disabled=false}};
checkHealth();
async function viewChecks(id){
 document.querySelector('#dialog-title').textContent='Kiểm tra cú pháp';
 try{const response=await apiFetch('/api/tasks/'+id+'/checks');const data=await response.json();if(!response.ok)throw Error(data.error);
 document.querySelector('#file-list').replaceChildren();document.querySelector('#download-file').hidden=true;
 const names={passed:'Đạt cú pháp ở các tệp được hỗ trợ',failed:'Phát hiện lỗi cú pháp',not_supported:'Chưa hỗ trợ kiểm tra các loại tệp này',unavailable:'Chưa kiểm tra được'};
 document.querySelector('#file-notice').textContent=(names[data.status]||data.status)+' · Đã kiểm tra: '+data.checked+' · Bỏ qua: '+data.skipped;
 document.querySelector('#file-content').textContent=data.message+(data.requirements?.issues?.length?'\n\nChưa đáp ứng yêu cầu:\n'+data.requirements.issues.join('\n'):'')+'\n\n'+data.findings.map(item=>item.path+' · '+({passed:'Đạt',failed:'Lỗi',skipped:'Bỏ qua',unavailable:'Chưa kiểm tra được'})[item.status]+'\n'+item.message).join('\n\n');document.querySelector('#file-dialog').showModal();
 }catch(e){document.querySelector('#error').textContent=e.message}
}
const templates={
 plan:{product:false,prompt:'Lập kế hoạch xây một ứng dụng quản lý công việc cá nhân. Nêu 3 tính năng cơ bản, các bước thực hiện và tiêu chí hoàn thành. Trả lời ngắn gọn bằng tiếng Việt.'},
 web:{product:true,prompt:'Tạo ứng dụng ghi chú bằng HTML, CSS và JavaScript thuần: thêm, sửa, xóa và tìm kiếm ghi chú; lưu bằng localStorage. Giao diện tiếng Việt, dùng được trên điện thoại. Không cần thư viện ngoài. Trả đầy đủ index.html, style.css, app.js và README.md hướng dẫn mở trang. Không tuyên bố đã chạy kiểm thử.'},
 python:{product:true,prompt:'Tạo ứng dụng quản lý việc cần làm trên dòng lệnh bằng Python 3.12, chỉ dùng thư viện chuẩn. Có thêm, liệt kê, đánh dấu hoàn thành; lưu dữ liệu vào JSON trong thư mục người dùng chọn. Không tự xóa tệp. Trả main.py, tests/test_main.py với unittest và README.md hướng dẫn chạy và kiểm thử bằng tiếng Việt.'},
 data:{product:true,prompt:'Tạo bộ tệp dữ liệu JSON mẫu cho ứng dụng ghi chú: notes.json chứa 3 ghi chú gồm id, title, content, created_at; config.json chứa cấu hình không có thông tin bí mật; README.md mô tả từng trường bằng tiếng Việt. Dùng JSON chuẩn, không comment hay dấu phẩy cuối.'}
};
let parentTask=null;
const DRAFT_KEY='bao-mat.draft.v1';
function showRequirements(){const files={web:'index.html, style.css, app.js, README.md',python:'main.py, tests/test_main.py, README.md',data:'notes.json (3 ghi chú), config.json, README.md'};document.querySelector('#template-requirements').textContent=parentTask?'Bản chỉnh sửa giữ bộ tiêu chí của bản gốc.':files[document.querySelector('#task-template').value]?'Tệp thực tế bắt buộc: '+files[document.querySelector('#task-template').value]+'. Chỉ hướng dẫn trong README chưa được tính là hoàn thành.':''}
function currentDraft(){return {prompt:document.querySelector('#prompt').value,mode:document.querySelector('#mode').value,product:document.querySelector('#product').checked,parent_id:parentTask,template:document.querySelector('#task-template').value}}
function persistDraft(){showRequirements();try{localStorage.setItem(DRAFT_KEY,JSON.stringify(currentDraft()));document.querySelector('#draft-status').textContent='Đã lưu nháp trên trình duyệt này. Không nhập khóa API vào yêu cầu.'}catch{document.querySelector('#draft-status').textContent='Trình duyệt không cho lưu nháp; hãy giữ lại yêu cầu trước khi đóng trang.'}}
function restoreDraft(){try{const saved=JSON.parse(localStorage.getItem(DRAFT_KEY)||'null');if(!saved){document.querySelector('#mode').value='ollama';return}if(typeof saved.prompt!=='string'||saved.prompt.length>4000||!['demo','ollama','ai'].includes(saved.mode))return;document.querySelector('#prompt').value=saved.prompt;document.querySelector('#mode').value=saved.mode;document.querySelector('#product').checked=saved.product===true;document.querySelector('#task-template').value=Object.hasOwn(templates,saved.template)?saved.template:'';if(typeof saved.parent_id==='string'&&/^[a-zA-Z0-9_-]{1,64}$/.test(saved.parent_id)){parentTask=saved.parent_id;document.querySelector('#revision-note').textContent='Tiếp tục soạn yêu cầu chỉnh sửa từ bản '+parentTask;document.querySelector('#revision-note').hidden=false;document.querySelector('#cancel-revision').hidden=false}document.querySelector('#draft-status').textContent='Đã khôi phục bản nháp và chế độ xử lý.'}catch{document.querySelector('#draft-status').textContent='Chưa đọc được bản nháp trên trình duyệt.'}}
for(const id of ['prompt','mode','product'])document.querySelector('#'+id).addEventListener(id==='prompt'?'input':'change',persistDraft);
document.querySelector('#clear-draft').onclick=()=>{if(document.querySelector('#prompt').value.trim()&&!confirm('Xóa yêu cầu đang soạn? Nhiệm vụ đã giao không bị xóa.'))return;document.querySelector('#prompt').value='';document.querySelector('#product').checked=false;document.querySelector('#task-template').value='';clearRevision()};
document.querySelector('#task-template').onchange=event=>{const template=templates[event.target.value];if(!template)return;if((document.querySelector('#prompt').value.trim()||parentTask)&&!confirm('Thay yêu cầu đang soạn bằng mẫu và bỏ chọn phiên bản gốc?')){event.target.value='';return}clearRevision();document.querySelector('#prompt').value=template.prompt;document.querySelector('#product').checked=template.product;document.querySelector('#prompt').focus();persistDraft()};
function clearRevision(){parentTask=null;document.querySelector('#revision-note').hidden=true;document.querySelector('#cancel-revision').hidden=true;persistDraft()}
document.querySelector('#cancel-revision').onclick=clearRevision;
async function beginRevision(task){
 try{const response=await apiFetch('/api/tasks/'+task.id+'/files');const data=await response.json();if(!response.ok)throw Error(data.error);
 parentTask=task.id;document.querySelector('#task-template').value='';document.querySelector('#product').checked=true;document.querySelector('#mode').value=task.mode;
 const note=document.querySelector('#revision-note');note.textContent='Đang sửa bản '+task.id+'. Bản gốc được giữ nguyên. Hãy nhập thay đổi bạn muốn.';note.hidden=false;
 document.querySelector('#cancel-revision').hidden=false;const prompt=document.querySelector('#prompt');prompt.value='';prompt.focus();prompt.scrollIntoView({behavior:'smooth',block:'center'});persistDraft();
 }catch(e){document.querySelector('#error').textContent=e.message}
}
async function viewDiff(id){
 document.querySelector('#dialog-title').textContent='So sánh phiên bản';
 try{const response=await apiFetch('/api/tasks/'+id+'/diff');const data=await response.json();if(!response.ok)throw Error(data.error);
 const list=document.querySelector('#file-list'),content=document.querySelector('#file-content');list.replaceChildren();document.querySelector('#download-file').hidden=true;
 document.querySelector('#file-notice').textContent='So với bản gốc '+data.parent_id+'. Các thay đổi do mô hình tạo, chưa được thực thi.';
 const names={added:'Thêm',deleted:'Xóa',modified:'Sửa'};
 for(const change of data.changes){const button=el('button',names[change.kind]+' · '+change.path);button.onclick=()=>{content.textContent=change.diff||'(Tệp rỗng)'};list.append(button)}
 content.textContent=data.changes.length?data.changes[0].diff:'Không có thay đổi nội dung tệp.';document.querySelector('#file-dialog').showModal();
 }catch(e){document.querySelector('#error').textContent=e.message}
}
const opened=new Set();
const memoryField=document.querySelector('#memory'),memoryStatus=document.querySelector('#memory-status');
document.querySelector('#save-memory').disabled=true;memoryField.disabled=true;
async function loadMemory(){try{const response=await apiFetch('/api/memory');if(!response.ok)throw Error('Không tải được bộ nhớ; hãy tải lại trang');const data=await response.json();memoryField.value=data.content;memoryField.disabled=false;document.querySelector('#save-memory').disabled=false}catch(e){memoryStatus.textContent=e.message}}
document.querySelector('#memory-form').onsubmit=async event=>{event.preventDefault();const button=document.querySelector('#save-memory');button.disabled=true;try{const response=await apiFetch('/api/memory',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:memoryField.value})});if(!response.ok)throw Error('Chưa lưu được bộ nhớ');memoryStatus.textContent='Đã lưu. Nhiệm vụ mới sẽ dùng bộ nhớ này.'}catch(e){memoryStatus.textContent=e.message}finally{button.disabled=false}};
loadMemory();
async function taskAction(id,action,button){
 const message=action==='cancel'?'Hủy nhiệm vụ? Ứng dụng sẽ đóng luồng Ollama và chuyển sang việc tiếp theo. Việc dừng tính bên trong máy chủ phụ thuộc Ollama. OpenAI hiện vẫn chờ yêu cầu kết thúc.':'Bạn đã xem và chấp nhận kết quả này? Việc duyệt không chạy hay triển khai mã.';
 if(!confirm(message))return;
 button.disabled=true;
 try{const response=await apiFetch('/api/tasks/'+id+'/'+action,{method:'POST'});const data=await response.json();if(!response.ok)throw Error(data.error);await refresh()}catch(e){document.querySelector('#error').textContent=e.message}finally{button.disabled=false}
}
async function retry(id,button){
 if(!confirm('Tạo một lượt chạy mới từ bước đầu và giữ nguyên kết quả cũ? OpenAI có thể phát sinh thêm phí; Ollama chạy trên máy.'))return;
 button.disabled=true;
 try{const response=await apiFetch('/api/tasks/'+id+'/retry',{method:'POST'});const data=await response.json();if(!response.ok)throw Error(data.error);await jumpTask(data.id)}
 catch(e){document.querySelector('#error').textContent=e.message}finally{button.disabled=false}
}
async function jumpTask(id){pageOffset=0;document.querySelector('#search').value=id;document.querySelector('#filter').value='all';await refresh()}
let submitting=false,queueFull=false,lastTaskSignature=null;
async function refresh(){const version=++refreshVersion;try{
 const params=new URLSearchParams({q:document.querySelector('#search').value,status:document.querySelector('#filter').value,offset:String(pageOffset)});
 const [response,teamResponse]=await Promise.all([apiFetch('/api/tasks?'+params),apiFetch('/api/team')]);
 if(!response.ok||!teamResponse.ok)throw Error('Không đọc được trạng thái đội bot');
 const data=await response.json(),team=await teamResponse.json();
 if(version!==refreshVersion)return;
 document.querySelector('#previous-page').disabled=pageOffset===0;
 document.querySelector('#next-page').disabled=pageOffset+data.limit>=data.total;
 document.querySelector('#page-info').textContent=data.tasks.length?'Kết quả '+(pageOffset+1)+'–'+Math.min(pageOffset+data.tasks.length,data.total)+' / '+data.total:'0 kết quả';
 document.querySelector('option[value="ai"]').disabled=!data.ai_available;
 if(!data.ai_available&&document.querySelector('#mode').value==='ai'){document.querySelector('#mode').value='demo';persistDraft();document.querySelector('#draft-status').textContent='OpenAI chưa cấu hình; chuyển sang mô phỏng. Bạn có thể chọn Ollama.'}
 const roles=document.querySelector('.roles');roles.replaceChildren();
 for(const bot of team.bots)roles.append(el('span',bot.name+' · '+(bot.active?bot.active+' nhiệm vụ đang làm':'Rảnh')));
 document.querySelector('#summary').textContent=(Object.entries(team.totals).map(([k,v])=>(labels[k]||k)+': '+v).join(' · ')||'Chưa có nhiệm vụ')+' · Hàng đợi: '+team.queue.waiting+'/'+team.queue.capacity;
 queuePaused=team.queue.paused;document.querySelector('#queue-state').textContent=(queuePaused?'Đang tạm dừng':'Sẵn sàng nhận việc')+' · '+team.queue.waiting+'/'+team.queue.capacity+' việc chờ';document.querySelector('#toggle-queue').textContent=queuePaused?'Tiếp tục hàng đợi':'Tạm dừng hàng đợi';document.querySelector('#toggle-queue').disabled=queueUpdating;
 queueFull=team.queue.waiting>=team.queue.capacity;document.querySelector('#submit').disabled=submitting||queueFull;
 const signature=JSON.stringify(data.tasks);if(signature===lastTaskSignature){updateDurations();return}lastTaskSignature=signature;
 const root=document.querySelector('#tasks');root.replaceChildren();
 const tasks=data.tasks;
 if(!tasks.length)root.append(el('p','Không có nhiệm vụ phù hợp. Thử đổi từ khóa hoặc bộ lọc.'));
 for(const t of tasks){
  const card=el('article','');card.append(el('h3',t.prompt),el('p',`${labels[t.status]||t.status} · ${t.stage} · ${t.mode==='demo'?'MÔ PHỎNG':t.mode==='ollama'?'OLLAMA':'OPENAI'} · ${new Date(t.created).toLocaleString('vi-VN')}`));
  const timing=el('p','');timing.className='progress-text';timing.dataset.duration='';timing.dataset.start=t.started_at||'';timing.dataset.finish=t.finished_at||'';timing.dataset.steps=String(t.completed_steps||0);card.append(timing);
  const history=el('button','Lịch sử từng bước');history.className='secondary';history.onclick=()=>viewHistory(t.id);card.append(history);
  const details=el('details','');details.open=opened.has(t.id);details.append(el('summary','Chi tiết và kết quả'));
  details.addEventListener('toggle',()=>{if(details.isConnected){if(details.open)opened.add(t.id);else opened.delete(t.id)}});
  details.append(el('small','Mã nhiệm vụ: '+t.id));
  if(t.retry_of){const previous=el('button','Xem lượt trước');previous.onclick=()=>jumpTask(t.retry_of);details.append(el('p','Chạy lại từ: '+t.retry_of),previous)}
  if(t.retry_id){const next=el('button','Xem lượt chạy lại');next.onclick=()=>jumpTask(t.retry_id);details.append(next)}
  if(t.requirements?.required_files?.length)details.append(el('h4','Tệp bắt buộc'),el('p',t.requirements.required_files.join(', ')));
  if(t.parent_id)details.append(el('p','Phiên bản sửa từ nhiệm vụ: '+t.parent_id));
  if(t.project_memory)details.append(el('h4','Bộ nhớ lúc giao việc'),el('pre',t.project_memory));
  const outputs=Object.entries(JSON.parse(t.output));
  if(!outputs.length)details.append(el('p','Chưa có kết quả.'));
  for(const [key,value] of outputs){details.append(el('h4',({plan:'Kế hoạch',result:'Kết quả',review:'Kiểm tra'})[key]||key),el('pre',key==='review'?reviewText(value):value));if(value){const link=el('a','Tải phần này (.md)');link.href='/api/tasks/'+t.id+'/export/'+key;details.append(link)}}
  if(outputs.some(([,value])=>value)){const link=el('a','Tải toàn bộ báo cáo (.md)');link.href='/api/tasks/'+t.id+'/export/all';card.append(link)}
  card.append(details);
  if(t.product&&['completed','needs_review','approved'].includes(t.status)){const button=el('button','Xem bộ tệp');button.onclick=()=>viewFiles(t.id);const link=el('a','Tải mã nguồn ZIP');link.href='/api/tasks/'+t.id+'/artifact.zip';const checks=el('button','Kiểm tra cú pháp');checks.onclick=()=>viewChecks(t.id);card.append(checks);const revise=el('button','Yêu cầu chỉnh sửa');revise.onclick=()=>beginRevision(t);card.append(button,link,revise);if(t.parent_id){const compare=el('button','So sánh với bản gốc');compare.onclick=()=>viewDiff(t.id);card.append(compare)}}
  if(['queued','running'].includes(t.status)){const button=el('button','Hủy nhiệm vụ');button.onclick=()=>taskAction(t.id,'cancel',button);card.append(button)}
  if(t.mode!=='demo'&&['completed','needs_review'].includes(t.status)&&JSON.parse(t.output).result){const button=el('button','Duyệt kết quả');button.onclick=()=>taskAction(t.id,'approve',button);card.append(button)}
  if(!t.retry_id&&['failed','interrupted','cancelled','needs_review'].includes(t.status)){const button=el('button','Chạy lại từ đầu');button.onclick=()=>retry(t.id,button);card.append(button)}
  root.append(card);
 }
 updateDurations();
 }catch(e){if(version===refreshVersion)document.querySelector('#error').textContent=e.message}}
let searchTimer;
document.querySelector('#search').oninput=()=>{clearTimeout(searchTimer);pageOffset=0;refreshVersion++;searchTimer=setTimeout(refresh,300)};
document.querySelector('#filter').onchange=()=>{pageOffset=0;refresh()};
document.querySelector('#previous-page').onclick=()=>{pageOffset=Math.max(0,pageOffset-50);refresh()};
document.querySelector('#next-page').onclick=()=>{pageOffset+=50;refresh()};
document.querySelector('#form').onsubmit=async event=>{
 event.preventDefault();const button=document.querySelector('#submit'),request=currentDraft();submitting=true;button.disabled=true;
 try{
  const response=await apiFetch('/api/tasks',{method:'POST',body:JSON.stringify(request)});const data=await response.json();if(!response.ok)throw Error(data.error);
  document.querySelector('#error').textContent='';
  if(JSON.stringify(currentDraft())===JSON.stringify(request)){document.querySelector('#prompt').value='';document.querySelector('#task-template').value='';clearRevision();persistDraft()}
  pageOffset=0;document.querySelector('#search').value='';document.querySelector('#filter').value='all';await refresh();
 }catch(error){document.querySelector('#error').textContent=error.message}
 finally{submitting=false;button.disabled=queueFull}
};
restoreDraft();showRequirements();refresh();setInterval(refresh,2000);
