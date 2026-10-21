const {test, expect} = require('@playwright/test');

async function post(page, path, payload) {
  const {token} = await (await page.request.get('/api/session')).json();
  const response = await page.request.post(path, {data: payload, headers: {'X-CSRF-Token':token}});
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function taskList(page, query) {
  await page.locator('[data-view="tasks"]').click();
  if (query !== undefined) {
    const loaded=page.waitForResponse(response=>{
      const url=new URL(response.url());
      return url.pathname==='/api/tasks' && response.request().method()==='GET' && url.searchParams.get('q')===query;
    });
    await page.locator('#search').fill(query);
    const data=await (await loaded).json();
    await expect(page.locator('#tasks article')).toHaveCount(data.tasks.length);
  }
}
async function moreActions(card) {
  if (!await card.locator('details').evaluate(node=>node.open)) await card.locator('summary').click();
}

test.beforeEach(async ({page}) => {
  page.on('dialog', dialog => dialog.accept());
  await post(page, '/api/queue', {paused:false});
  await page.goto('/');
  await expect(page.locator('#toggle-queue')).toBeEnabled();
  await expect(page.locator('#app-version')).toContainText('commit');
});

test('per-file workflow with a fixture provider shows three files and request counts', async ({page}) => {
  await page.locator('#task-template').selectOption('data');
  await page.locator('#mode').selectOption('ollama');
  await page.locator('#prompt').fill('Kiểm thử sinh từng tệp trên trình duyệt');
  await page.locator('#submit').click();
  await taskList(page);
  const card=page.locator('#tasks article').filter({hasText:'Kiểm thử sinh từng tệp trên trình duyệt'});
  await expect(card).toContainText('AI đánh giá đạt');
  await expect(card).toContainText('Sinh từng tệp riêng · 6 lượt yêu cầu mô hình');
  await expect(card).toContainText('ECC · Dữ liệu JSON → Đội thực thi · lượt gọi 6/20');
  await card.getByRole('button',{name:'Xem bộ tệp',exact:true}).click();
  await expect(page.locator('#product-files button')).toHaveText(['notes.json','config.json','README.md']);
  const download=page.waitForEvent('download');
  await page.locator('#product-download-zip').click();
  expect((await download).suggestedFilename()).toMatch(/^product-.*\.zip$/);
});

test('restores a draft and provider after reload; failed submit keeps draft', async ({page}) => {
  await page.locator('#mode').selectOption('ollama');
  await page.locator('#product').check();
  await page.locator('#prompt').fill('Yêu cầu tiếng Việt chưa giao');
  await page.reload();
  await expect(page.locator('#prompt')).toHaveValue('Yêu cầu tiếng Việt chưa giao');
  await expect(page.locator('#mode')).toHaveValue('ollama');
  await expect(page.locator('#product')).toBeChecked();
  await page.route('**/api/tasks', route => route.request().method()==='POST' ? route.fulfill({status:429,contentType:'application/json',body:JSON.stringify({error:'Hàng đợi đầy thử nghiệm'})}) : route.continue());
  await page.locator('#submit').click();
  await expect(page.locator('#error')).toContainText('Hàng đợi đầy');
  await page.reload();
  await expect(page.locator('#prompt')).toHaveValue('Yêu cầu tiếng Việt chưa giao');
});

test('pause, submit demo, resume and inspect actual step history', async ({page}) => {
  await page.locator('#toggle-queue').click();
  await expect(page.locator('#queue-state')).toContainText('Đang tạm dừng');
  await page.locator('#mode').selectOption('demo');
  await page.locator('#prompt').fill('Kiểm tra tạm dừng bằng trình duyệt');
  await page.locator('#submit').click();
  await taskList(page);
  const card = page.locator('#tasks article').filter({hasText:'Kiểm tra tạm dừng bằng trình duyệt'});
  await expect(card).toContainText('Chờ');
  await expect(card.getByRole('button',{name:'Xóa công việc',exact:true})).toHaveCount(0);
  await page.waitForTimeout(500);
  await expect(card).not.toContainText('Hoàn thành mô phỏng');
  await page.locator('#toggle-queue').click();
  await expect(card).toContainText('Hoàn thành mô phỏng');
  await expect(card.getByRole('button',{name:'Xóa công việc',exact:true})).toBeVisible();
  await expect(card.locator('[data-duration]')).toContainText('Đã xong 4 bước');
  await moreActions(card);
  await card.getByRole('button',{name:'Lịch sử từng bước'}).click();
  await expect(page.locator('#file-dialog')).toBeVisible();
  await expect(page.locator('#dialog-title')).toHaveText('Lịch sử từng bước');
  await expect(page.locator('#file-list button')).toHaveCount(4);
  await page.locator('#file-list button').filter({hasText:'Điều phối'}).click();
  await expect(page.locator('#file-content')).toContainText('Kiểm tra tạm dừng bằng trình duyệt');
});

test('product preview, download, checks and revision draft survive reload', async ({page}) => {
  await page.locator('#task-template').selectOption('data');
  await expect(page.locator('#template-requirements')).toContainText('notes.json');
  await expect(page.locator('#product')).toBeChecked();
  await expect(page.locator('#product')).toBeDisabled();
  await expect(page.locator('#output-kind')).toContainText('tạo bộ tệp');
  await page.locator('#mode').selectOption('demo');
  await page.locator('#prompt').fill('Sản phẩm mô phỏng kiểm thử giao diện');
  await page.locator('#submit').click();
  await taskList(page);
  const card=page.locator('#tasks article').filter({hasText:'Sản phẩm mô phỏng kiểm thử giao diện'});
  await expect(card).toContainText('Hoàn thành mô phỏng');
  await expect(card).toContainText('notes.json, config.json, README.md');
  await card.getByRole('button',{name:'Xem bộ tệp',exact:true}).click();
  await expect(page.locator('#product-editor')).toHaveValue(/Sản phẩm mô phỏng/);
  const downloaded=page.waitForEvent('download');
  await page.locator('#product-download-file').click();
  expect((await downloaded).suggestedFilename()).toBe('README.md');
  await taskList(page);
  await moreActions(card);
  await card.getByRole('button',{name:'Kiểm tra cú pháp'}).click();
  await expect(page.locator('#file-notice')).toContainText('Chưa hỗ trợ');
  await page.locator('#close-files').click();
  await card.getByRole('button',{name:'Yêu cầu chỉnh sửa'}).click();
  await page.locator('#prompt').fill('Thêm hướng dẫn sử dụng tiếng Việt');
  await page.reload();
  await expect(page.locator('#revision-note')).toBeVisible();
  await expect(page.locator('#prompt')).toHaveValue('Thêm hướng dẫn sử dụng tiếng Việt');
});

test('polling preserves expanded result and does not recreate unchanged cards', async ({page}) => {
  const result=await post(page,'/api/tasks',{prompt:'Kết quả giữ nguyên khi làm mới',mode:'demo'});
  await taskList(page, result.id);
  const card=page.locator('#tasks article').filter({hasText:'Kết quả giữ nguyên khi làm mới'});
  await expect(card).toContainText('Hoàn thành mô phỏng');
  // The worker records final timing after setting the terminal status. Only
  // assert unchanged DOM once the complete row snapshot has stopped changing.
  await expect(card.locator('[data-duration]')).not.toHaveAttribute('data-finish', '');
  await card.locator('summary').click();
  await card.evaluate(node=>node.dataset.testMarker='original');
  await page.waitForTimeout(2300);
  await expect(card).toHaveAttribute('data-test-marker','original');
  await expect(card.locator('details')).toHaveAttribute('open','');
});

test('desktop and mobile layouts have no horizontal overflow or script errors', async ({page}) => {
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.reload();
  await expect(page.locator('#submit')).toBeEnabled();
  await page.setViewportSize({width:390,height:844});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
  expect(overflow).toBe(false);
  expect(errors).toEqual([]);
});

test('cleanup previews, requires typed confirmation, preserves final output and downloads backup', async ({page}) => {
  await page.locator('[data-view="settings"]').click();
  await page.locator('#preview-cleanup').click();
  await expect(page.locator('#cleanup-summary')).toContainText('1 nội dung lượt');
  await expect(page.locator('#cleanup-examples')).toContainText('cleanup-fixture');
  await expect(page.locator('#apply-cleanup')).toBeDisabled();
  await page.locator('#cleanup-confirmation').fill('DON');
  await expect(page.locator('#apply-cleanup')).toBeDisabled();
  await page.locator('#cleanup-confirmation').fill('DỌN');
  await page.locator('#apply-cleanup').click();
  await expect(page.locator('#cleanup-status')).toContainText('Đã dọn 1 mục');
  const download=page.waitForEvent('download');
  await page.locator('#cleanup-backup').click();
  expect((await download).suggestedFilename()).toMatch(/^cleanup-.*\.zip$/);
  await taskList(page, 'cleanup-fixture');
  const card=page.locator('#tasks article').filter({hasText:'Nhiệm vụ cũ để kiểm thử dọn'});
  await card.locator('summary').click();
  await card.getByRole('button',{name:'Mở kết quả',exact:true}).click();
  await expect(page.locator('#inspector-output')).toContainText('Kết quả cuối cần giữ');
  await taskList(page);
  await moreActions(card);
  await card.getByRole('button',{name:'Lịch sử từng bước'}).click();
  await expect(page.locator('#file-content')).toContainText('Nội dung lượt này đã được dọn');
  await page.locator('#close-files').click();
  await page.locator('[data-view="settings"]').click();
  await page.locator('#cleanup-scope').selectOption('tasks');
  await page.locator('#preview-cleanup').click();
  await expect(page.locator('#cleanup-summary')).toContainText('1 nhiệm vụ');
  await page.locator('#cleanup-confirmation').fill('DỌN');
  await page.locator('#cleanup-days').fill('60');
  await expect(page.locator('#apply-cleanup')).toBeDisabled();
  await expect(page.locator('#cleanup-preview')).toBeHidden();
  await page.locator('#preview-cleanup').click();
  await page.locator('#cleanup-confirmation').fill('DỌN');
  await page.locator('#apply-cleanup').click();
  await expect(page.locator('#cleanup-status')).toContainText('Đã dọn 1 mục');
  await taskList(page);
  await expect(card).toHaveCount(0);
});

test('resource controls persist policy and bounded expert work can retry with more calls', async ({page}) => {
  await page.locator('[data-view="resources"]').click();
  await expect(page.locator('#resource-memory')).toContainText('GiB');
  await expect(page.locator('#resource-scope')).toContainText('máy chủ ứng dụng');
  await page.locator('#default-call-limit').fill('3');
  await page.locator('#max-waiting').fill('2');
  await page.locator('#save-resources').click();
  await expect(page.locator('#resource-status')).toContainText('Đã lưu');
  await expect(page.locator('#queue-state')).toContainText('/2 việc chờ');
  try {
    await page.locator('[data-view="workspace"]').click();
    await page.getByText('Chuyên gia, lượt gọi và tài liệu đính kèm',{exact:true}).click();
    await page.locator('#task-template').selectOption('data');
    await page.locator('#mode').selectOption('ollama');
    await page.locator('#call-limit').fill('3');
    await page.locator('#prompt').fill('Kiểm thử sinh từng tệp trên trình duyệt');
    await page.locator('#submit').click();
    await taskList(page);
    const card=page.locator('#tasks article').filter({hasText:'Kiểm thử sinh từng tệp trên trình duyệt'}).first();
    await expect(card).toContainText('Đã dùng hết giới hạn lượt gọi');
    await expect(card).toContainText('lượt gọi 3/3');
    await card.getByRole('button',{name:'Xem bộ tệp',exact:true}).click();
    await expect(page.locator('#product-files button')).toHaveText(['notes.json']);
    page.removeAllListeners('dialog');
    page.on('dialog',dialog=>dialog.type()==='prompt'?dialog.accept('6'):dialog.accept());
    await taskList(page);
    await moreActions(card);
    await card.getByRole('button',{name:'Chạy lại từ đầu'}).click();
    await expect(card).toContainText('AI đánh giá đạt');
    await expect(card).toContainText('lượt gọi 6/6');
  } finally {
    await post(page,'/api/resource-policy',{default_call_limit:20,max_waiting:10});
  }
});

test('all nine team members explain their roles and individual setup persists', async ({page}) => {
  await page.locator('[data-view="team"]').click();
  await expect(page.locator('.bot-card')).toHaveCount(9);
  const python=page.locator('[data-bot-id="python"]');
  await expect(python).toContainText('CHUYÊN GIA ECC');
  await expect(python).toContainText('Sẵn sàng khi được chọn');
  await python.getByRole('button',{name:'Thiết lập bot',exact:true}).click();
  await page.locator('#bot-name').fill('Chuyên gia Python của tôi');
  await page.locator('#bot-instructions').fill('Giải thích ngắn bằng tiếng Việt.');
  await page.locator('#save-bot').click();
  await expect(page.locator('#bot-save-status')).toContainText('Đã lưu');
  await page.locator('#close-bot').click();
  await page.reload();
  await expect(python).toContainText('Chuyên gia Python của tôi');
  await python.getByRole('button',{name:'Giao việc cho chuyên gia này'}).click();
  await expect(page.locator('#expert')).toHaveValue('python');
  await expect(page.locator('#view-workspace')).toBeVisible();
  await post(page,'/api/bots',{id:'python',name:'Python',instructions:''});
});

test('documents import, edit, attach to a task and delete without changing task history', async ({page}) => {
  await page.locator('[data-view="documents"]').click();
  await page.locator('#document-import').setInputFiles({name:'yeu-cau.md',mimeType:'text/markdown',buffer:Buffer.from('# Yêu cầu\nDùng tiếng Việt có dấu.')});
  await expect(page.locator('#document-content')).toHaveValue('# Yêu cầu\nDùng tiếng Việt có dấu.');
  await page.locator('#document-title').fill('Tài liệu đính kèm thử nghiệm');
  await page.locator('#save-document').click();
  await expect(page.locator('#document-status')).toContainText('Đã lưu');
  await page.locator('[data-view="workspace"]').click();
  await page.getByText('Chuyên gia, lượt gọi và tài liệu đính kèm',{exact:true}).click();
  await page.locator('#document-choices').getByLabel('Tài liệu đính kèm thử nghiệm').check();
  await page.locator('#mode').selectOption('demo');
  await page.locator('#prompt').fill('Việc có tài liệu để đọc lại');
  await page.reload();
  await page.getByText('Chuyên gia, lượt gọi và tài liệu đính kèm',{exact:true}).click();
  await expect(page.locator('#document-choices').getByLabel('Tài liệu đính kèm thử nghiệm')).toBeChecked();
  const created=page.waitForResponse(response=>response.url().endsWith('/api/tasks') && response.request().method()==='POST');
  await page.locator('#submit').click();
  const task=await (await created).json();
  await taskList(page);
  const card=page.locator('#tasks article').filter({hasText:'Việc có tài liệu để đọc lại'});
  await expect(card).toContainText('Đính kèm: Tài liệu đính kèm thử nghiệm');
  await page.locator('[data-view="documents"]').click();
  await page.locator('.document-item').filter({hasText:'Tài liệu đính kèm thử nghiệm'}).click();
  await page.locator('#delete-document').click();
  await expect(page.locator('#document-status')).toContainText('Đã xóa');
  await expect(page.locator('.document-item').filter({hasText:'Tài liệu đính kèm thử nghiệm'})).toHaveCount(0);
  const original=await (await page.request.get('/api/tasks/'+task.id)).json();
  expect(original.documents[0].title).toBe('Tài liệu đính kèm thử nghiệm');
  const report=await (await page.request.get('/api/tasks/'+task.id+'/export/all')).text();
  expect(report).toContain('Dùng tiếng Việt có dấu.');
});

test('static web preview blocks scripts and network, editor saves a new version', async ({page}) => {
  let externalRequests=0;
  await page.route('https://outside.test/**',route=>{externalRequests++;return route.abort();});
  await taskList(page, 'web-preview-fixture');
  const card=page.locator('#tasks article').filter({hasText:'Trang mẫu để duyệt và chỉnh sửa'});
  await card.getByRole('button',{name:'Xem bộ tệp',exact:true}).click();
  await expect(page.locator('#product-files button')).toHaveCount(4);
  await page.locator('#tab-preview').click();
  const frame=page.frameLocator('#product-preview');
  await expect(frame.locator('h1')).toHaveText('Trang xem trước tiếng Việt');
  await expect(frame.locator('body')).toHaveCSS('background-color','rgb(1, 2, 3)');
  expect(await page.evaluate(()=>window.previewExecuted)).toBeUndefined();
  await expect(page.locator('#product-preview')).toHaveAttribute('sandbox','');
  expect(externalRequests).toBe(0);
  await page.locator('#tab-code').click();
  await page.locator('#product-files').getByRole('button',{name:'style.css',exact:true}).click();
  await page.locator('#product-editor').fill('body { background: rgb(10, 20, 30); color: white; }');
  await page.waitForTimeout(2300);
  await expect(page.locator('#product-editor')).toHaveValue('body { background: rgb(10, 20, 30); color: white; }');
  await page.locator('#tab-preview').click();
  await expect(frame.locator('body')).toHaveCSS('background-color','rgb(10, 20, 30)');
  await page.locator('#preview-mobile').click();
  await expect(page.locator('#preview-mobile')).toHaveAttribute('aria-pressed','true');
  await page.locator('#tab-code').click();
  await page.locator('#save-product').click();
  await expect(page.locator('#editor-state')).toContainText('Đã lưu phiên bản mới');
  await expect(page.locator('#inspector-status')).toContainText('Cần bạn xem');
  const link=await page.locator('#product-download-zip').getAttribute('href');
  const revisionId=link.split('/')[3];
  expect(revisionId).not.toBe('web-preview-fixture');
  const oldFiles=await (await page.request.get('/api/tasks/web-preview-fixture/files')).json();
  expect(oldFiles.files.find(file=>file.path==='style.css').content).toContain('rgb(1, 2, 3)');
  const revision=await (await page.request.get('/api/tasks/'+revisionId)).json();
  expect(revision.model_calls).toBe(0);
  expect(revision.generation_method).toBe('manual');
  expect(externalRequests).toBe(0);
  await page.locator('#expand-inspector').click();
  await expect(page.locator('.workspace-grid')).toHaveClass(/expanded/);
  await expect(page.locator('.work-feed')).toBeHidden();
  await page.locator('#expand-inspector').click();
  await expect(page.locator('.work-feed')).toBeVisible();
  await page.locator('#close-inspector').click();
  await expect(page.locator('#inspector-empty')).toBeVisible();
  await expect(page.locator('#product-editor')).toHaveValue('');
});

test('each section is usable on a narrow screen without horizontal overflow', async ({page}) => {
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.setViewportSize({width:390,height:844});
  for(const view of ['tasks','team','documents','resources','settings','workspace']) {
    await page.locator('[data-view="'+view+'"]').click();
    await expect(page.locator('#view-'+view)).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth)).toBe(false);
  }
  expect(errors).toEqual([]);
});

test('icons navigate, work history stays separate and only compact summaries load', async ({page}) => {
  const lists=[];
  page.on('response',async response=>{
    const url=new URL(response.url());
    if(url.pathname==='/api/tasks' && response.request().method()==='GET') {
      lists.push({compact:url.searchParams.get('compact'),data:await response.json()});
    }
  });
  await page.reload();
  await expect(page.locator('#view-workspace')).toBeVisible();
  await page.waitForTimeout(2300);
  expect(lists).toHaveLength(0);
  await expect(page.locator('#tasks article')).toHaveCount(0);
  expect(await page.locator('#view-workspace #task-section').count()).toBe(0);
  await page.locator('[data-view="tasks"] span').click();
  await page.locator('#stat-review').click();
  await expect(page.locator('#view-tasks')).toBeVisible();
  await expect(page.locator('#filter')).toHaveValue('needs_review');
  await expect.poll(()=>lists.length).toBeGreaterThan(0);
  expect(lists.every(item=>item.compact==='1')).toBe(true);
  for(const {data} of lists) {
    expect(data.limit).toBe(20);
    expect(data.tasks.every(task=>!('output' in task) && !('project_memory' in task))).toBe(true);
  }
  await page.locator('[data-view="team"] span').click();
  await page.locator('[data-bot-id="python"] .bot-avatar').click();
  await expect(page.locator('#bot-dialog')).toBeVisible();
  await page.locator('#close-bot').click();
  await page.locator('[data-view="resources"] span').click();
  await expect(page.locator('#view-resources')).toBeVisible();
  await page.locator('[data-view="tasks"] span').click();
  await expect(page.locator('#view-tasks')).toBeVisible();
  await page.locator('[data-view="workspace"] span').click();
  await expect(page.locator('#tasks article')).toHaveCount(0);
  await page.waitForTimeout(250);
  const count=lists.length;
  await page.waitForTimeout(2300);
  expect(lists.length).toBe(count);
});

test('delete beside downloads previews, cancels, backs up and clears the selected workbench', async ({page}) => {
  const task=await post(page,'/api/tasks',{prompt:'Công việc để xóa riêng trên giao diện',mode:'demo'});
  await taskList(page,task.id);
  const card=page.locator('#tasks article').filter({hasText:'Công việc để xóa riêng trên giao diện'});
  await expect(card).toContainText('Hoàn thành mô phỏng');
  await expect(card.locator('.task-row-actions').getByRole('link',{name:'Tải báo cáo'})).toBeVisible();
  await card.getByRole('button',{name:'Xóa công việc',exact:true}).click();
  await expect(page.locator('#confirm-task-delete')).toBeEnabled();
  await expect(page.locator('#task-delete-summary')).toContainText('riêng công việc này');
  await page.locator('#cancel-task-delete').click();
  expect((await page.request.get('/api/tasks/'+task.id)).status()).toBe(200);
  await card.getByRole('button',{name:'Mở kết quả',exact:true}).click();
  await expect(page.locator('#inspector-body')).toBeVisible();
  await page.locator('#delete-open-task').click();
  await expect(page.locator('#confirm-task-delete')).toBeEnabled();
  await page.locator('#confirm-task-delete').click();
  await expect(page.locator('#workspace-notice')).toContainText('Đã xóa công việc');
  await expect(page.locator('#inspector-empty')).toBeVisible();
  await expect(page.locator('#inspector-body')).toBeHidden();
  expect((await page.request.get('/api/tasks/'+task.id)).status()).toBe(404);
  const download=page.waitForEvent('download');
  await page.locator('#task-delete-backup').click();
  expect((await download).suggestedFilename()).toMatch(/^task-delete-.*\.zip$/);
  await taskList(page,task.id);
  await expect(page.locator('#tasks article')).toHaveCount(0);
});

test('deleting a source keeps another version and its source comparison usable', async ({page}) => {
  const parent=await post(page,'/api/tasks',{prompt:'Bản gốc để xóa nhưng giữ phiên bản',mode:'demo',product:true});
  await expect.poll(async()=> (await (await page.request.get('/api/tasks/'+parent.id)).json()).status).toBe('completed');
  const child=await post(page,'/api/tasks/'+parent.id+'/edit',{files:[{path:'README.md',content:'# Nội dung phiên bản cần giữ'}]});
  await taskList(page,parent.id);
  await page.locator('#tasks article[data-task-id="'+parent.id+'"]').getByRole('button',{name:'Xóa công việc',exact:true}).click();
  await expect(page.locator('#task-delete-summary')).toContainText('1 công việc liên quan');
  await page.locator('#confirm-task-delete').click();
  await expect(page.locator('#workspace-notice')).toContainText('Đã xóa công việc');
  await page.locator('#search').fill(child.id);
  const card=page.locator('#tasks article');
  await expect(card).toContainText('Chỉnh sửa thủ công');
  await moreActions(card);
  await expect(card).toContainText('Bản gốc đã xóa');
  await card.getByRole('button',{name:'So sánh với bản gốc'}).click();
  await expect(page.locator('#file-content')).toContainText('Nội dung phiên bản cần giữ');
});

test('a failed action reports an error in the visible work list', async ({page}) => {
  await taskList(page,'web-preview-fixture');
  const card=page.locator('#tasks article');
  await moreActions(card);
  await page.route('**/api/tasks/web-preview-fixture/checks',route=>route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({error:'Bộ kiểm tra đang bận thử nghiệm; hãy thử lại.'})}));
  await card.getByRole('button',{name:'Kiểm tra cú pháp',exact:true}).click();
  await expect(page.locator('#view-tasks')).toBeVisible();
  await expect(page.locator('#workspace-notice')).toBeVisible();
  await expect(page.locator('#workspace-notice')).toContainText('Bộ kiểm tra đang bận');
});

test('project and model settings reach a run and stay frozen after model edits', async ({page}) => {
  await page.locator('[data-view="settings"]').click();
  await expect(page.locator('#platform-status')).toContainText('API 1');
  await page.locator('#profile-id').fill('browser-local');
  await page.locator('#profile-name').fill('Model kiểm thử');
  await page.locator('#profile-model').fill('qwen3:4b');
  await page.locator('#model-profile-form button[type="submit"], #model-profile-form button:not([type])').click();
  await expect(page.locator('#model-profile-status')).toContainText('phiên bản 1');
  await page.locator('[data-view="team"]').click();
  await page.locator('[data-bot-id="result"]').getByRole('button',{name:'Thiết lập bot',exact:true}).click();
  await expect(page.locator('#save-bot')).toBeEnabled();
  await page.locator('#bot-model-ollama').selectOption('browser-local');
  await page.locator('#save-bot').click();
  await expect(page.locator('#bot-save-status')).toContainText('Đã lưu');
  await page.locator('#close-bot').click();
  await page.locator('[data-view="settings"]').click();
  await page.locator('#project-id').fill('browser-project');
  await page.locator('#project-name').fill('Dự án kiểm thử');
  await page.locator('#project-memory').fill('Giữ bộ nhớ riêng');
  await page.locator('#project-profile-form button').click();
  await expect(page.locator('#project-profile-status')).toContainText('Đã lưu');
  await page.locator('[data-view="workspace"]').click();
  await page.locator('#task-project').selectOption('browser-project');
  await page.locator('#task-template').selectOption('data');
  await page.locator('#mode').selectOption('ollama');
  await page.locator('#prompt').fill('Kiểm thử sinh từng tệp trên trình duyệt');
  await page.locator('#submit').click();
  await expect(page.locator('#inspector-status')).toContainText('AI đánh giá đạt');
  await page.locator('#run-workspace summary').click();
  await expect(page.locator('#run-config')).toContainText('browser-project/');
  await expect(page.locator('#run-config')).toContainText('browser-local v1');
  await page.locator('[data-view="settings"]').click();
  await page.locator('#profile-picker').selectOption('browser-local');
  await page.locator('#profile-model').fill('changed-model');
  await page.locator('#model-profile-form button:not([type])').click();
  await expect(page.locator('#model-profile-status')).toContainText('phiên bản 2');
  await page.locator('[data-view="workspace"]').click();
  await expect(page.locator('#run-config')).toContainText('browser-local v1');
  await expect(page.locator('#run-config')).not.toContainText('changed-model');
});

test('product checks report unsupported web execution and unknown commands stay actionable', async ({page}) => {
  await page.evaluate(() => window.WorkspaceUI.openTask('web-preview-fixture'));
  await page.locator('#run-workspace summary').click();
  await page.locator('#run-product-tests').click();
  await expect(page.locator('#run-tests-status')).toContainText('not_supported');
  await expect(page.locator('#run-checks-output')).toContainText('Chưa có tệp unittest Python');
  await page.locator('#prompt').fill('/tdd something');
  await page.locator('#submit').click();
  await expect(page.locator('#error')).toContainText('Lệnh chưa hỗ trợ');
  await expect(page.locator('#prompt')).toHaveValue('/tdd something');
});

test('revision draft survives reload while source validation is still pending', async ({page}) => {
  await page.evaluate(() => window.WorkspaceUI.openTask('web-preview-fixture'));
  await page.route('**/api/tasks/web-preview-fixture/files', async (route) => {
    await new Promise(resolve => setTimeout(resolve, 800));
    try { await route.continue(); } catch {}
  });
  await page.locator('#ask-revision').click();
  await page.locator('#prompt').fill('Nháp phải giữ trước khi phản hồi về');
  await page.reload();
  await expect(page.locator('#revision-note')).toBeVisible();
  await expect(page.locator('#revision-note')).toContainText('web-preview-fixture');
  await expect(page.locator('#prompt')).toHaveValue('Nháp phải giữ trước khi phản hồi về');
});

test('failed workspace script keeps controls disabled and explains how to recover', async ({page}) => {
  await page.route('**/workspace_ui.js', route => route.abort('failed'));
  await page.reload();
  await expect(page.locator('#workspace-notice')).toContainText('Chưa tải đủ giao diện');
  await expect(page.locator('[data-view="resources"]')).toBeDisabled();
  await expect(page.locator('#toggle-queue')).toBeDisabled();
  await expect(page.locator('#submit')).toBeDisabled();
  await page.unroute('**/workspace_ui.js');
  await page.reload();
  await expect(page.locator('#toggle-queue')).toBeEnabled();
  await page.locator('[data-view="resources"]').click();
  await expect(page.locator('#view-resources')).toBeVisible();
  await expect(page.locator('#default-call-limit')).toBeEditable();
});

test('bot capability controls enforce a denial and show a content-free audit trail', async ({page}) => {
  const before = (await (await page.request.get('/api/bots')).json()).bots.find(bot=>bot.id==='plan');
  await page.locator('[data-view="team"]').click();
  const card = page.locator('[data-bot-id="plan"]');
  await card.getByRole('button',{name:'Thiết lập bot',exact:true}).click();
  await expect(page.locator('#save-bot')).toBeEnabled();
  await page.locator('[data-bot-tool="generate_text"]').uncheck();
  await page.locator('#save-bot').click();
  await expect(page.locator('#bot-save-status')).toContainText('Đã lưu');
  await page.locator('#close-bot').click();
  try {
    const task = await post(page,'/api/tasks',{prompt:'Kiểm thử sinh từng tệp trên trình duyệt',mode:'ollama',expert:'none'});
    await expect.poll(async()=> (await (await page.request.get('/api/tasks/'+task.id)).json()).status).toBe('needs_review');
    await page.evaluate(id=>window.WorkspaceUI.openTask(id),task.id);
    await expect(page.locator('#inspector-body')).toBeVisible();
    await page.locator('#run-workspace > summary').click();
    await page.locator('#inspect-audit').click();
    await page.locator('#audit-decision').selectOption('BLOCK');
    await expect(page.locator('#audit-events')).toContainText('Bị chặn');
    await expect(page.locator('#audit-events')).toContainText('Gọi model');
    await expect(page.locator('#audit-events')).toContainText('Đã từ chối');
    await expect(page.locator('#audit-events')).not.toContainText('Kiểm thử sinh từng tệp trên trình duyệt');
    await expect(page.locator('#audit-status')).toContainText('1 sự kiện');
  } finally {
    await post(page,'/api/bots',{id:before.id,name:before.name,instructions:before.instructions,tools:before.tools});
  }
});

test('upgrade review creates an isolated candidate, downloads it and deletes only the proposal', async ({page}) => {
  await page.locator('[data-view="settings"]').click();
  await page.locator('#upgrade-panel > summary').click();
  await page.locator('#upgrade-task').fill('web-preview-fixture');
  await page.locator('#upgrade-title').fill('Nâng cấp thử bằng trình duyệt');
  await page.locator('#upgrade-create').click();
  await expect(page.locator('#upgrade-status')).toContainText('Đã lưu bản sao và patch');
  await expect(page.locator('#upgrade-detail')).toBeVisible();
  await expect(page.locator('#upgrade-detail h4')).toContainText(['index.html','style.css','app.js','README.md']);
  await expect(page.locator('#upgrade-detail')).toContainText('chưa chạy toàn bộ kiểm thử');
  const downloading = page.waitForEvent('download');
  await page.locator('#upgrade-detail a').click();
  expect((await downloading).suggestedFilename()).toMatch(/^upgrade-.*\.zip$/);
  await page.locator('#upgrade-detail').getByRole('button',{name:'Duyệt bản đề xuất',exact:true}).click();
  await expect(page.locator('#upgrade-detail')).toContainText('Bạn đã duyệt · chưa áp dụng');
  const proposal = page.locator('#upgrade-list article').filter({hasText:'Nâng cấp thử bằng trình duyệt'});
  await proposal.getByRole('button',{name:'Xóa bản đề xuất',exact:true}).click();
  await expect(proposal).toHaveCount(0);
  await expect(page.locator('#upgrade-status')).toContainText('Đã xóa bản đề xuất');
  await page.reload();
  await expect(page.locator('#submit')).toBeEnabled();
  expect((await page.request.get('/api/tasks/web-preview-fixture')).ok()).toBeTruthy();
});

test('audit and proposal details remain usable on a narrow screen', async ({page}) => {
  const proposal=await post(page,'/api/upgrades',{task_id:'web-preview-fixture',title:'Đối chiếu trên điện thoại'});
  await page.setViewportSize({width:390,height:844});
  await page.locator('[data-view="settings"]').click();
  await page.locator('#upgrade-panel > summary').click();
  await page.locator('#upgrade-list article').filter({hasText:'Đối chiếu trên điện thoại'}).getByRole('button',{name:'Xem thay đổi',exact:true}).click();
  await expect(page.locator('#upgrade-detail')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.locator('#upgrade-detail').screenshot({path:process.env.BAO_REVIEW_SCREENSHOT_DIR ? process.env.BAO_REVIEW_SCREENSHOT_DIR+'/proposal-mobile.png' : 'test-results/proposal-mobile.png'});
  await page.locator('[data-view="resources"]').click();
  await page.locator('#audit-panel > summary').click();
  await expect(page.locator('#audit-events article').first()).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.locator('#audit-panel').screenshot({path:process.env.BAO_REVIEW_SCREENSHOT_DIR ? process.env.BAO_REVIEW_SCREENSHOT_DIR+'/audit-mobile.png' : 'test-results/audit-mobile.png'});
  await post(page,'/api/upgrades/'+proposal.id+'/delete',{confirmation:proposal.id});
});

test('custom required files and product kind survive reload with a budget estimate', async ({page}) => {
  await page.locator('#product').check();
  await page.locator('#product-contract > summary').click();
  await page.locator('#required-files').fill('src/main.py\ntests/test_main.py\nREADME.md');
  await expect(page.locator('#contract-budget')).toContainText('ít nhất 6 lượt gọi');
  await page.locator('#prompt').fill('Bản nháp có danh sách tệp riêng');
  await page.reload();
  await page.locator('#product-contract > summary').click();
  await expect(page.locator('#required-files')).toHaveValue('src/main.py\ntests/test_main.py\nREADME.md');
  await expect(page.locator('#product-kind')).toHaveValue('application');
  await page.locator('#product-kind').selectOption('documents');
  await page.locator('#required-files').fill('README.md');
  await page.reload();
  await page.locator('#product-contract > summary').click();
  await expect(page.locator('#product-kind')).toHaveValue('documents');
  await expect(page.locator('#required-files')).toHaveValue('README.md');
});

test('custom planning generates actual files and downloads bounded evidence without claiming function tests', async ({page}) => {
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.locator('#product').check();
  await page.locator('#mode').selectOption('ollama');
  await page.locator('#prompt').fill('Kiểm thử danh sách tệp tự nhập');
  await page.locator('#submit').click();
  await expect(page.locator('#quality-summary')).toContainText('Đủ tệp, đạt cú pháp');
  await expect(page.locator('#quality-completeness')).toContainText('Đạt');
  await expect(page.locator('#quality-execution')).toContainText('Chưa chạy');
  await page.locator('#tab-code').click();
  await expect(page.locator('#product-files button')).toHaveText(['main.py','tests/test_main.py','README.md']);
  const downloading=page.waitForEvent('download');
  await page.locator('#quality-download').click();
  const saved=await downloading;
  expect(saved.suggestedFilename()).toMatch(/^quality-.*\.json$/);
  const fs=require('node:fs/promises');
  const evidence=JSON.parse(await fs.readFile(await saved.path(),'utf8'));
  expect(evidence.complete).toBe(true);expect(evidence.functional_verified).toBe(false);
  expect(evidence.content_sha256).toMatch(/^[a-f0-9]{64}$/);
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.locator('#product-quality').screenshot({path:process.env.BAO_REVIEW_SCREENSHOT_DIR ? process.env.BAO_REVIEW_SCREENSHOT_DIR+'/quality-mobile.png' : 'test-results/quality-mobile.png'});
  expect(errors).toEqual([]);
});

test('incomplete product offers missing-only repair and preserves the original README', async ({page}) => {
  await taskList(page,'incomplete-product-fixture');
  await page.locator('#tasks article').getByRole('button',{name:'Xem bộ tệp',exact:true}).click();
  await expect(page.locator('#quality-summary')).toContainText('Bộ tệp chưa đạt');
  await expect(page.locator('#product-download-zip')).toContainText('chưa đạt');
  await page.locator('#repair-missing').click();
  await expect(page.locator('#prompt')).toHaveValue(/Bổ sung.*main.py/);
  await page.reload();
  await expect(page.locator('#revision-note')).toBeVisible();
  await page.locator('#submit').click();
  await expect(page.locator('#quality-summary')).toContainText('Đủ tệp, đạt cú pháp');
  await page.locator('#tab-code').click();
  await page.locator('#product-files button').filter({hasText:'README.md'}).click();
  await expect(page.locator('#product-editor')).toHaveValue('# Giữ nguyên hướng dẫn gốc');
  const original=await (await page.request.get('/api/tasks/incomplete-product-fixture/files')).json();
  expect(original.files).toEqual([{path:'README.md',content:'# Giữ nguyên hướng dẫn gốc'}]);
});

test('README-only application is rejected while explicit documents remain supported', async ({page}) => {
  await page.locator('#product').check();
  await page.locator('#product-contract > summary').click();
  await page.locator('#required-files').fill('README.md');
  await page.locator('#prompt').fill('Kiểm thử danh sách tệp tự nhập');
  await page.locator('#submit').click();
  await expect(page.locator('#error')).toContainText('mã nguồn thực tế');
  await expect(page.locator('#prompt')).toHaveValue('Kiểm thử danh sách tệp tự nhập');
  await page.locator('#product-kind').selectOption('documents');
  await page.locator('#submit').click();
  await expect(page.locator('#quality-completeness')).toContainText('Đạt');
  await expect(page.locator('#quality-syntax')).toContainText('Chưa hỗ trợ');
  await expect(page.locator('#quality-execution')).toContainText('Chưa chạy');
});
