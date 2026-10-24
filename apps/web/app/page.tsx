"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDownToLine, ArrowRight, Check, ChevronDown, FileImage, Globe2, Languages, LoaderCircle, Moon, ShieldCheck, Upload, X } from "lucide-react";

const CONFIGURED_API = process.env.NEXT_PUBLIC_API_URL?.trim();
const LOCAL_API = Boolean(CONFIGURED_API && /^https?:\/\/(localhost|127(?:\.\d{1,3}){3}|\[::1\])(?::\d+)?(?:\/|$)/i.test(CONFIGURED_API));
const API = process.env.NODE_ENV === "development"
  ? CONFIGURED_API || "http://localhost:8000"
  : LOCAL_API ? "" : CONFIGURED_API || "";
const TEXT = {
  en: { convert: "Convert files", downloader: "Download media", formats: "Supported formats", jobs: "My jobs", help: "Help", headline: "Your files, ready for what comes next.", intro: "A careful, straightforward workspace for the formats you need.", image: "File converter", private: "Private by default", privateBody: "Files are processed for this request and are not added to a public library.", drop: "Drop a file here, or", browse: "choose a file", supported: "Images, audio, and video · images up to 20 MB, media up to 100 MB", output: "Convert to", action: "Convert file", working: "Converting…", done: "Your converted file is ready.", again: "Convert another", download: "Download file", source: "Input format", choose: "Select a file to inspect its actual format.", downloaderTitle: "Download from a platform", notReady: "Paste a public platform video URL. The link does not need a .mp4 extension. We’ll check the available qualities.", downloadDisabled: "This server has no active platform downloader. Install yt-dlp and ffprobe, or enable downloads in its configuration.", apiOffline: "The processing API could not be reached. Check this deployment’s /api/health endpoint; if it fails too, the Vercel API service is not running.", analyze: "Check again", paste: "Paste", pasteError: "Clipboard access was unavailable. Paste the URL into the field.", mediaDownload: "Download video", mediaDone: "Your media file is ready.", mediaError: "Could not analyze this link. It may be unsupported, unavailable, or restricted.", available: "Available now", sitefoot: "A small utility, built around clear capabilities and careful handling.", error: "We couldn’t process that file. Check its format, size, and integrity.", formatsIntro: "Image, audio, and video conversions available on this server.", formatsBody: "PNG, JPEG, and WebP convert between those formats. Audio converts to MP3, WAV, FLAC, AAC, M4A, OGG, or Opus where the encoder is installed. Video converts to MP4, WebM, MOV, or MKV, or can be extracted to audio. Animated images and unsupported codecs are rejected.", recent: "Recent results stay in this page until you leave it. No account or server-side job history is implemented yet.", privacy: "Files are sent to the configured OpenConvert API and processed for this request. Results are not stored as persistent jobs. This local version has no analytics.", inspecting: "Inspecting file…", inspectFailed: "Inspection unavailable", lossy: "Re-encoded", lossless: "Lossless", analyzing: "Checking available formats…", quality: "Quality", optionAudio: "Audio only" },
  ar: { convert: "تحويل الملفات", downloader: "تنزيل الوسائط", formats: "الصيغ المدعومة", jobs: "ملفاتي", help: "المساعدة", headline: "ملفاتك، جاهزة للخطوة التالية.", intro: "مساحة بسيطة ودقيقة للصيغ التي تحتاجها.", image: "محوّل الملفات", private: "خصوصيتك أولاً", privateBody: "تُعالج الملفات لهذا الطلب فقط ولا تُضاف إلى مكتبة عامة.", drop: "أفلت ملفاً هنا، أو", browse: "اختر ملفاً", supported: "صور وصوت وفيديو · الصور حتى 20 م.ب والوسائط حتى 100 م.ب", output: "التحويل إلى", action: "حوّل الملف", working: "جارٍ التحويل…", done: "ملفك المحوّل جاهز.", again: "تحويل ملف آخر", download: "تنزيل الملف", source: "صيغة الملف", choose: "اختر ملفاً لفحص صيغته الفعلية.", downloaderTitle: "تنزيل من منصة", notReady: "الصق رابط فيديو عام من منصة. لا يلزم أن ينتهي الرابط بـ ‎.mp4؛ سنفحص الجودات المتاحة.", downloadDisabled: "لا تتوفر أداة تنزيل منصات على هذا الخادم. ثبّت yt-dlp وffprobe أو فعّل التنزيل من الإعدادات.", apiOffline: "تعذّر الوصول إلى خدمة المعالجة. افحص /api/health على هذا النشر؛ إذا لم يفتح أيضاً، فخدمة API على Vercel لا تعمل.", analyze: "أعد الفحص", paste: "لصق", pasteError: "تعذّر الوصول إلى الحافظة. الصق الرابط في الحقل.", mediaDownload: "تنزيل الفيديو", mediaDone: "ملف الوسائط جاهز.", mediaError: "تعذّر فحص الرابط. قد تكون المنصة غير مدعومة أو أن المحتوى غير متاح أو مقيّداً.", available: "متاح الآن", sitefoot: "أداة بسيطة، بإمكانيات واضحة ومعالجة مسؤولة.", error: "تعذّرت معالجة الملف. تحقق من صيغته وحجمه وسلامته.", formatsIntro: "تحويل الصور والصوت والفيديو المتاح على هذا الخادم.", formatsBody: "تدعم الصور PNG وJPEG وWebP. يمكن تحويل الصوت إلى MP3 وWAV وFLAC وAAC وM4A وOGG وOpus وفق المشفّرات المثبتة. ويمكن تحويل الفيديو إلى MP4 وWebM وMOV وMKV أو استخراج الصوت. تُرفض الصور المتحركة والصيغ غير المدعومة.", recent: "تبقى النتائج في هذه الصفحة حتى مغادرتها. لا يوجد حساب أو سجل للمهام على الخادم حالياً.", privacy: "تُرسل الملفات إلى واجهة OpenConvert المحددة وتُعالج لهذا الطلب، ولا تُحفظ كمهام دائمة. لا تستخدم هذه النسخة تحليلات.", inspecting: "جارٍ فحص الملف…", inspectFailed: "تعذّر فحص الملف", lossy: "إعادة ترميز", lossless: "دون فقدان", analyzing: "جارٍ فحص الجودات المتاحة…", quality: "الجودة", optionAudio: "الصوت فقط" }
};

export default function Home() {
  const [lang, setLang] = useState<"en" | "ar">("en");
  const t = TEXT[lang];
  const [file, setFile] = useState<File | null>(null);
  const [format, setFormat] = useState("PNG");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ url: string; name: string } | null>(null);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [dark, setDark] = useState(false);
  const [inspection, setInspection] = useState<{ format: string; family: string; outputs: string[]; width?: number | null; height?: number | null } | null>(null);
  const [inspecting, setInspecting] = useState(false);
  const [mediaUrl, setMediaUrl] = useState("");
  const [mediaInfo, setMediaInfo] = useState<{ title:string; extractor:string; duration:number|null; options:{key:string;kind:string;height:number|null;label:string;has_audio:boolean}[] } | null>(null);
  const [mediaBusy, setMediaBusy] = useState(false);
  const [mediaError, setMediaError] = useState(false);
  const [mediaOption, setMediaOption] = useState("");
  const [downloadEnabled, setDownloadEnabled] = useState(false);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [imageLimitMb, setImageLimitMb] = useState(20);
  const [mediaLimitMb, setMediaLimitMb] = useState(100);
  const [formatRegistry, setFormatRegistry] = useState<{verified:boolean;image_pairs:{input:string;output:string}[];audio_pairs:{input:string;output:string}[];video_pairs:{input:string;output:string}[];engine_versions?:{pillow?:string;ffmpeg?:string}} | null>(null);
  const [resultMessage, setResultMessage] = useState(t.done);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const savedLang = localStorage.getItem("openconvert-language");
    const savedTheme = localStorage.getItem("openconvert-theme");
    if (savedLang === "ar" || savedLang === "en") setLang(savedLang);
    if (savedTheme === "dark") setDark(true);
  }, []);
  useEffect(() => { document.documentElement.lang = lang; document.documentElement.dir = lang === "ar" ? "rtl" : "ltr"; }, [lang]);
  useEffect(() => {
    fetch(`${API}/api/capabilities`).then(r => r.ok ? r.json() : null).then(data => {
      setApiOnline(Boolean(data));
      setDownloadEnabled(Boolean(data?.media_downloader?.enabled));
      if (Number.isFinite(data?.max_image_upload_bytes)) setImageLimitMb(Math.max(1, Math.floor(data.max_image_upload_bytes / 1024 / 1024)));
      if (Number.isFinite(data?.max_upload_bytes)) setMediaLimitMb(Math.max(1, Math.floor(data.max_upload_bytes / 1024 / 1024)));
    }).catch(() => {setApiOnline(false);setDownloadEnabled(false)});
    fetch(`${API}/api/formats`).then(r => r.ok ? r.json() : null).then(data => setFormatRegistry(data?.verified ? data : null)).catch(() => setFormatRegistry(null));
  }, []);
  const accept = async (candidate?: File) => {
    if (!candidate) return;
    if (result) URL.revokeObjectURL(result.url);
    setFile(candidate); setResult(null); setError(""); setInspection(null); setInspecting(true);
    try {
      const body = new FormData(); body.append("file", candidate);
      const response = await fetch(`${API}/api/inspect`, { method: "POST", body });
      if (!response.ok) throw new Error("inspection failed");
      const info = await response.json(); setInspection(info); setFormat(info.outputs[0]);
    } catch (cause) { setError(cause instanceof TypeError ? t.apiOffline : t.error); setFile(null); }
    finally { setInspecting(false); }
  };
  const convert = async () => {
    if (!file || busy) return;
    setBusy(true); setError("");
    try {
      const body = new FormData(); body.append("file", file); body.append("output_format", format);
      const response = await fetch(`${API}/api/convert`, { method: "POST", body });
      if (!response.ok) throw new Error("conversion failed");
      const blob = await response.blob();
      const disposition = response.headers.get("content-disposition") || "";
      const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
      const name = (encodedName ? decodeURIComponent(encodedName) : null) || disposition.match(/filename="?([^";]+)"?/i)?.[1] || `converted.${format.toLowerCase()}`;
      setResultMessage(t.done);
      setResult({ url: URL.createObjectURL(blob), name });
    } catch (cause) { setError(cause instanceof TypeError ? t.apiOffline : t.error); } finally { setBusy(false); }
  };
  const analyzeMedia = async () => {
    setMediaBusy(true); setMediaError(false); setMediaInfo(null);
    try {
      const response = await fetch(`${API}/api/download/analyze`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({url: mediaUrl}) });
      if (!response.ok) throw new Error("unsupported platform link");
      const info = await response.json();
      setMediaInfo(info); setMediaOption(info.options?.[0]?.key || "");
    } catch { setMediaError(true); }
    finally { setMediaBusy(false); }
  };
  useEffect(() => {
    if (!downloadEnabled || !mediaUrl.trim()) return;
    let controller: AbortController | null = null;
    const timer = window.setTimeout(async () => {
      controller = new AbortController(); setMediaBusy(true); setMediaError(false); setMediaInfo(null); setMediaOption("");
      try {
        const response = await fetch(`${API}/api/download/analyze`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:mediaUrl.trim()}),signal:controller.signal});
        if (!response.ok) throw new Error("platform analysis failed");
        const info = await response.json(); setMediaInfo(info); setMediaOption(info.options?.[0]?.key || "");
      } catch (cause) { if (!(cause instanceof DOMException && cause.name === "AbortError")) setMediaError(true); }
      finally { if (!controller?.signal.aborted) setMediaBusy(false); }
    }, 700);
    return () => {window.clearTimeout(timer); controller?.abort();};
  }, [mediaUrl,downloadEnabled]);
  const pasteMediaUrl = async () => {
    try {
      const value = await navigator.clipboard.readText();
      if (!value.trim()) throw new Error("empty clipboard");
      setMediaUrl(value.trim()); setMediaInfo(null); setMediaError(false);
    } catch { setMediaError(true); }
  };
  const downloadMedia = async () => {
    setMediaBusy(true); setMediaError(false);
    try {
      const response = await fetch(`${API}/api/download`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({url: mediaUrl,option:mediaOption}) });
      if (!response.ok) throw new Error("download failed");
      const blob = await response.blob();
      const disposition = response.headers.get("content-disposition") || "";
      const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
      const name = encodedName ? decodeURIComponent(encodedName) : "downloaded-media";
      if (result) URL.revokeObjectURL(result.url);
      setResultMessage(t.mediaDone);
      setResult({url: URL.createObjectURL(blob), name});
    } catch { setMediaError(true); }
    finally { setMediaBusy(false); }
  };
  const describePairs = (pairs: {input:string;output:string}[]) => {
    const grouped = new Map<string,string[]>();
    for (const pair of pairs) grouped.set(pair.input, [...(grouped.get(pair.input) || []), pair.output]);
    return [...grouped.entries()].map(([source,outputs]) => `${source} → ${[...new Set(outputs)].join(", ")}`).join(" · ");
  };
  return <main data-theme={dark ? "dark" : "light"} lang={lang} dir={lang === "ar" ? "rtl" : "ltr"}>
    <header className="topbar"><a className="brand" href="#top" aria-label="OpenConvert home"><span className="brand-icon"><FileImage size={19}/></span><span>Open<span className="brand-light">Convert</span></span></a><nav aria-label="Main navigation"><a className="active" href="#convert">{t.convert}</a><a href="#download">{t.downloader}</a><a href="#formats">{t.formats}</a><a href="#jobs">{t.jobs}</a><a href="#help">{t.help}</a></nav><div className="tools"><button className="icon-btn" aria-label="Toggle theme" title="Theme" onClick={() => {const next = !dark; setDark(next); localStorage.setItem("openconvert-theme", next ? "dark" : "light")}}><Moon size={17}/></button><button className="language" onClick={() => {const next = lang === "en" ? "ar" : "en"; setLang(next); localStorage.setItem("openconvert-language", next)}}><Languages size={16}/>{lang === "en" ? "العربية" : "English"}</button></div></header>
    <section className="intro" id="top"><div className="eyebrow"><span/> FILES, WITHOUT THE FUSS</div><h1>{t.headline}</h1><p>{t.intro}</p></section>
    <section className="workspace" id="convert"><div className="workspace-main"><div className="section-head"><div><div className="kicker">01 / CONVERT</div><h2>{t.image}</h2></div><span className="capability"><span/> {t.available}</span></div>
      <div className={`dropzone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`} onDragEnter={e => {e.preventDefault(); setDragging(true)}} onDragOver={e => e.preventDefault()} onDragLeave={e => {e.preventDefault(); setDragging(false)}} onDrop={e => {e.preventDefault(); setDragging(false); accept(e.dataTransfer.files[0])}}>
        {file ? <><span className="file-icon"><FileImage size={21}/></span><div className="file-details"><strong dir="auto" title={file.name}>{file.name}</strong><span>{(file.size / 1024 / 1024).toFixed(2)} MB · {inspection ? `${inspection.format}${inspection.width && inspection.height ? ` · ${inspection.width} × ${inspection.height}` : ` · ${inspection.family}`}` : inspecting ? t.inspecting : t.inspectFailed}</span></div><button className="remove" onClick={() => {setFile(null); setResult(null); setInspection(null)}} aria-label="Remove selected file"><X size={18}/></button></> : <><span className="upload-icon"><Upload size={20}/></span><div><strong>{t.drop} <button className="text-btn" onClick={() => input.current?.click()}>{t.browse}</button></strong><span className="subline">{lang === "ar" ? `صور وصوت وفيديو · الصور حتى ${imageLimitMb} م.ب والوسائط حتى ${mediaLimitMb} م.ب` : `Images, audio, and video · images up to ${imageLimitMb} MB, media up to ${mediaLimitMb} MB`}</span></div></>}
        <input ref={input} type="file" accept="image/*,audio/*,video/*,.avif,.gif,.tiff,.tif,.bmp,.mkv,.avi,.mov,.mp4,.m4a,.mp3,.wav,.flac,.ogg,.opus,.aac" hidden onChange={e => accept(e.target.files?.[0])}/>
      </div>
      {file && inspection && <div className="controls"><label htmlFor="format">{t.output}</label><div className="select-wrap"><select id="format" value={format} onChange={e => setFormat(e.target.value)}>{inspection.outputs.map(option => <option value={option} key={option}>{option === "JPEG" ? "JPEG" : option === "WEBP" ? "WebP" : option}</option>)}</select><ChevronDown size={15}/></div><span className="loss-note">{["PNG","WAV","FLAC"].includes(format) ? t.lossless : t.lossy}</span></div>}
      {error && <div className="error" role="alert">{error}</div>}
      {result ? <div className="result" role="status"><span className="success-icon"><Check size={17}/></span><span>{resultMessage}</span><a className="primary-btn" href={result.url} download={result.name}><ArrowDownToLine size={16}/>{t.download}</a><button className="again" onClick={() => {URL.revokeObjectURL(result.url); setResult(null); setFile(null); setInspection(null)}}>{t.again}</button></div> : <button className="primary-btn convert-btn" disabled={!file || !inspection || busy || inspecting} onClick={convert}>{busy ? <LoaderCircle className="spin" size={17}/> : <ArrowRight className="directional" size={17}/>} {busy ? t.working : t.action}</button>}
      <div className="fineprint"><ShieldCheck size={15}/><span>{t.private}</span><span className="dot-divider">·</span><span>{t.privateBody}</span></div>
    </div><aside className="workspace-side"><div className="side-block"><div className="kicker">THE PROCESS</div><ol className="steps"><li><span>1</span><div><b>Choose a file</b><small>We inspect its real format</small></div></li><li><span>2</span><div><b>Pick an output</b><small>Only working options appear</small></div></li><li><span>3</span><div><b>Download</b><small>We validate the converted file</small></div></li></ol></div><div className="side-block source-block"><div className="kicker">{t.source.toUpperCase()}</div><div className="source-value">{file ? <><span className="format-chip">{inspection?.format || "…"}</span><span>{inspection ? "Content detected" : t.inspecting}</span></> : <span className="muted">{t.choose}</span>}</div></div><div className="side-foot"><ShieldCheck size={16}/><span>Files are processed privately<br/>and held only for this request.</span></div></aside></section>
    <section className="download-panel" id="download"><div className="download-label"><span className="kicker">02 / DOWNLOAD</span><span className="status-pill">{apiOnline === false ? "API OFFLINE" : downloadEnabled ? "LIVE LINK CHECK" : "CHECKING"}</span></div><div className="download-content"><h2>{t.downloaderTitle}</h2><p>{apiOnline === false ? <>{t.apiOffline} <a href="/api/health" target="_blank" rel="noreferrer">/api/health</a></> : downloadEnabled ? t.notReady : t.downloadDisabled}</p><div className="url-form"><input aria-label="Media platform URL" type="url" dir="ltr" inputMode="url" placeholder="https://www.youtube.com/watch?v=…" value={mediaUrl} onChange={e => {setMediaUrl(e.target.value); setMediaInfo(null); setMediaOption(""); setMediaError(false)}}/><button className="primary-btn paste-btn" onClick={pasteMediaUrl}>{t.paste}</button><button className="primary-btn" disabled={!downloadEnabled || !mediaUrl || mediaBusy} onClick={analyzeMedia}>{mediaBusy ? <LoaderCircle className="spin" size={16}/> : <Globe2 size={15}/>} {t.analyze}</button></div>{mediaBusy && <p className="analysis-status" role="status"><LoaderCircle className="spin" size={14}/>{t.analyzing}</p>}{mediaError && <p className="error" role="alert">{t.mediaError}</p>}{mediaInfo && <div className="platform-result"><div className="platform-meta"><strong dir="auto">{mediaInfo.title}</strong><small>{mediaInfo.extractor}{mediaInfo.duration ? ` · ${Math.floor(mediaInfo.duration / 60)}:${String(Math.floor(mediaInfo.duration % 60)).padStart(2,"0")}` : ""}</small></div><div className="media-options"><label htmlFor="media-quality">{t.quality}</label><div className="select-wrap"><select id="media-quality" value={mediaOption} onChange={e => setMediaOption(e.target.value)}>{mediaInfo.options.map(option => <option value={option.key} key={option.key}>{option.kind === "audio" ? t.optionAudio : option.label}</option>)}</select><ChevronDown size={15}/></div><button className="primary-btn" disabled={mediaBusy || !mediaOption} onClick={downloadMedia}>{mediaBusy ? <LoaderCircle className="spin" size={16}/> : <ArrowDownToLine size={16}/>} {t.mediaDownload}</button></div></div>}</div><Globe2 className="globe" size={27}/></section>
    <section className="info-sections" id="formats"><div><span className="kicker">{t.formats.toUpperCase()}</span><h2>{formatRegistry ? t.formatsIntro : (lang === "ar" ? "سجل الصيغ الموثقة غير متاح حالياً." : "Verified format registry is unavailable.")}</h2></div>{formatRegistry && <div className="registry-list"><p><b>Images</b><span>{describePairs(formatRegistry.image_pairs)}</span></p><p><b>Audio</b><span>{describePairs(formatRegistry.audio_pairs)}</span></p><p><b>Video & audio extraction</b><span>{describePairs(formatRegistry.video_pairs)}</span></p><small>{formatRegistry.engine_versions?.pillow} · {formatRegistry.engine_versions?.ffmpeg}</small></div>}<div id="jobs"><span className="kicker">{t.jobs.toUpperCase()}</span><p>{t.recent}</p></div><div id="help"><span className="kicker">{t.help.toUpperCase()} & PRIVACY</span><p>{t.privacy}</p></div></section>
    <footer><a className="brand footer-brand" href="#top"><span className="brand-icon"><FileImage size={17}/></span>Open<span className="brand-light">Convert</span></a><span>{t.sitefoot}</span><div><a href="#formats">{t.formats}</a><a href="#help">{t.help}</a><a href="#help">Privacy</a></div></footer>
  </main>;
}
