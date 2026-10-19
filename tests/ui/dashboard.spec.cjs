const {test, expect} = require('@playwright/test');

async function post(page, path, payload) {
  const {token} = await (await page.request.get('/api/session')).json();
  const response = await page.request.post(path, {data: payload, headers: {'X-CSRF-Token':token}});
  expect(response.ok()).toBeTruthy();
  return response.json();
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
  const card=page.locator('#tasks article').filter({hasText:'Kiểm thử sinh từng tệp trên trình duyệt'});
  await expect(card).toContainText('AI đánh giá đạt');
  await expect(card).toContainText('Sinh từng tệp riêng · 6 lượt yêu cầu mô hình');
  await expect(card).toContainText('ECC · Dữ liệu JSON → Đội thực thi · lượt gọi 6/20');
  await card.getByRole('button',{name:'Xem bộ tệp',exact:true}).click();
  await expect(page.locator('#product-files button')).toHaveText(['notes.json','config.json','README.md']);
  const download=page.waitForEvent('download');
  await card.getByRole('link',{name:'Tải mã nguồn ZIP'}).click();
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
  const card = page.locator('#tasks article').filter({hasText:'Kiểm tra tạm dừng bằng trình duyệt'});
  await expect(card).toContainText('Chờ');
  await page.waitForTimeout(500);
  await expect(card).not.toContainText('Hoàn thành mô phỏng');
  await page.locator('#toggle-queue').click();
  await expect(card).toContainText('Hoàn thành mô phỏng');
  await expect(card.locator('[data-duration]')).toContainText('Đã xong 4 bước');
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
  const card=page.locator('#tasks article').filter({hasText:'Sản phẩm mô phỏng kiểm thử giao diện'});
  await expect(card).toContainText('Hoàn thành mô phỏng');
  await expect(card).toContainText('notes.json, config.json, README.md');
  await card.getByRole('button',{name:'Xem bộ tệp',exact:true}).click();
  await expect(page.locator('#product-editor')).toHaveValue(/Sản phẩm mô phỏng/);
  const downloaded=page.waitForEvent('download');
  await page.locator('#product-download-file').click();
  expect((await downloaded).suggestedFilename()).toBe('README.md');
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
  await page.locator('#search').fill(result.id);
  const card=page.locator('#tasks article').filter({hasText:'Kết quả giữ nguyên khi làm mới'});
  await expect(card).toContainText('Hoàn thành mô phỏng');
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
  await page.locator('[data-view="workspace"]').click();
  await page.locator('#search').fill('cleanup-fixture');
  const card=page.locator('#tasks article').filter({hasText:'Nhiệm vụ cũ để kiểm thử dọn'});
  await card.locator('summary').click();
  await expect(card).toContainText('Kết quả cuối cần giữ');
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
    await page.locator('.advanced-compose summary').click();
    await page.locator('#task-template').selectOption('data');
    await page.locator('#mode').selectOption('ollama');
    await page.locator('#call-limit').fill('3');
    await page.locator('#prompt').fill('Kiểm thử sinh từng tệp trên trình duyệt');
    await page.locator('#submit').click();
    const card=page.locator('#tasks article').filter({hasText:'Kiểm thử sinh từng tệp trên trình duyệt'}).first();
    await expect(card).toContainText('Đã dùng hết giới hạn lượt gọi');
    await expect(card).toContainText('lượt gọi 3/3');
    await card.getByRole('button',{name:'Xem bộ tệp',exact:true}).click();
    await expect(page.locator('#product-files button')).toHaveText(['notes.json']);
    page.removeAllListeners('dialog');
    page.on('dialog',dialog=>dialog.type()==='prompt'?dialog.accept('6'):dialog.accept());
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
  await page.locator('.advanced-compose summary').click();
  await page.locator('#document-choices').getByLabel('Tài liệu đính kèm thử nghiệm').check();
  await page.locator('#mode').selectOption('demo');
  await page.locator('#prompt').fill('Việc có tài liệu để đọc lại');
  await page.reload();
  await page.locator('.advanced-compose summary').click();
  await expect(page.locator('#document-choices').getByLabel('Tài liệu đính kèm thử nghiệm')).toBeChecked();
  const created=page.waitForResponse(response=>response.url().endsWith('/api/tasks') && response.request().method()==='POST');
  await page.locator('#submit').click();
  const task=await (await created).json();
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
  await page.locator('#search').fill('web-preview-fixture');
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
});

test('each section is usable on a narrow screen without horizontal overflow', async ({page}) => {
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.setViewportSize({width:390,height:844});
  for(const view of ['team','documents','resources','settings','workspace']) {
    await page.locator('[data-view="'+view+'"]').click();
    await expect(page.locator('#view-'+view)).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth)).toBe(false);
  }
  expect(errors).toEqual([]);
});
