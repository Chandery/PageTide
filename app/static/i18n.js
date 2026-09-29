/**
 * i18n.js - Internationalization framework
 *
 * Simple client-side i18n for PaperDigHelper.
 * Language packs are loaded from JSON files.
 */

const i18n = {
  currentLang: 'zh-CN',
  translations: {},

  async init(lang = 'zh-CN') {
    this.currentLang = lang;
    await this.loadLanguage(lang);
  },

  async loadLanguage(lang) {
    try {
      const res = await fetch(`/i18n/${lang}.json`);
      this.translations = await res.json();
    } catch (err) {
      console.error(`Failed to load language pack: ${lang}`, err);
      // Fallback to Chinese if loading fails
      if (lang !== 'zh-CN') {
        await this.loadLanguage('zh-CN');
      }
    }
  },

  t(key, fallback = key) {
    const keys = key.split('.');
    let value = this.translations;

    for (const k of keys) {
      if (value && typeof value === 'object' && k in value) {
        value = value[k];
      } else {
        return fallback;
      }
    }

    return typeof value === 'string' ? value : fallback;
  },

  async setLanguage(lang) {
    await this.loadLanguage(lang);
    this.currentLang = lang;
    // Trigger a custom event for components to update
    document.dispatchEvent(new CustomEvent('languagechange', { detail: { lang } }));
  },

  getCurrentLanguage() {
    return this.currentLang;
  }
};

// Auto-detect language from settings or browser
(async function() {
  let lang = localStorage.getItem('pdh-language');
  if (!lang) {
    const browserLang = navigator.language || navigator.userLanguage;
    lang = browserLang.startsWith('zh') ? 'zh-CN' : 'en-US';
  }
  await i18n.init(lang);
})();
