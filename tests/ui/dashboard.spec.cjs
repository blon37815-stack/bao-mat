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
  await expect(page.locator('#file-list button')).toHaveText(['notes.json','config.json','README.md']);
  await page.locator('#close-files').click();
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
  await expect(page.locator('#file-content')).toContainText('Sản phẩm mô phỏng');
  const downloaded=page.waitForEvent('download');
  await page.locator('#download-file').click();
  expect((await downloaded).suggestedFilename()).toBe('README.md');
  await page.locator('#close-files').click();
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
  await page.getByText('Kết nối và dữ liệu',{exact:true}).click();
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
  await page.locator('#search').fill('cleanup-fixture');
  const card=page.locator('#tasks article').filter({hasText:'Nhiệm vụ cũ để kiểm thử dọn'});
  await card.locator('summary').click();
  await expect(card).toContainText('Kết quả cuối cần giữ');
  await card.getByRole('button',{name:'Lịch sử từng bước'}).click();
  await expect(page.locator('#file-content')).toContainText('Nội dung lượt này đã được dọn');
  await page.locator('#close-files').click();
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
  await expect(page.locator('#resource-memory')).toContainText('GiB');
  await expect(page.locator('#resource-scope')).toContainText('máy chủ ứng dụng');
  await page.locator('#default-call-limit').fill('3');
  await page.locator('#max-waiting').fill('2');
  await page.locator('#save-resources').click();
  await expect(page.locator('#resource-status')).toContainText('Đã lưu');
  await expect(page.locator('#queue-state')).toContainText('/2 việc chờ');
  try {
    await page.locator('#task-template').selectOption('data');
    await page.locator('#mode').selectOption('ollama');
    await page.locator('#call-limit').fill('3');
    await page.locator('#prompt').fill('Kiểm thử sinh từng tệp trên trình duyệt');
    await page.locator('#submit').click();
    const card=page.locator('#tasks article').filter({hasText:'Kiểm thử sinh từng tệp trên trình duyệt'}).first();
    await expect(card).toContainText('Đã dùng hết giới hạn lượt gọi');
    await expect(card).toContainText('lượt gọi 3/3');
    await card.getByRole('button',{name:'Xem bộ tệp',exact:true}).click();
    await expect(page.locator('#file-list button')).toHaveText(['notes.json']);
    await page.locator('#close-files').click();
    page.removeAllListeners('dialog');
    page.on('dialog',dialog=>dialog.type()==='prompt'?dialog.accept('6'):dialog.accept());
    await card.getByRole('button',{name:'Chạy lại từ đầu'}).click();
    await expect(card).toContainText('AI đánh giá đạt');
    await expect(card).toContainText('lượt gọi 6/6');
  } finally {
    await post(page,'/api/resource-policy',{default_call_limit:20,max_waiting:10});
  }
});
