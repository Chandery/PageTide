(function(root) {
  'use strict';
  root.PTSaveFile = async function(filename, content) {
    const invoke = root.__TAURI_INTERNALS__?.invoke;
    if (invoke) {
      const receipt = JSON.parse(await invoke('save_export', {filename, content}));
      if (!['saved', 'cancelled'].includes(receipt.status)) throw new Error('导出未返回保存结果');
      return receipt;
    }
    if (root.showSaveFilePicker) {
      try {
        const handle = await root.showSaveFilePicker({suggestedName: filename});
        const writer = await handle.createWritable();
        await writer.write(content); await writer.close();
        return {status: 'saved', path: handle.name};
      } catch (error) {
        if (error.name === 'AbortError') return {status: 'cancelled'};
        throw error;
      }
    }
    throw new Error('当前浏览器不能确认文件保存，请在桌面应用中导出');
  };
})(typeof window !== 'undefined' ? window : globalThis);
