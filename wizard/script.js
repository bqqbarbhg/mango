import htm from "https://unpkg.com/htm?module"
// import { h, Fragment, render, createState, useState, useRef, useEffect } from "https://unpkg.com/kaiku"
import { h, Fragment, render, createState, useState, useRef, useEffect, immutable } from "./kaiku.min.js"

const html = htm.bind(h)

function setupFormsDefaults() {
    return {
        settings: {
            enabled: true,
            alwaysEnabled: true,
            id: "settings",
            title: "Settings",
            threads: Math.ceil(navigator.hardwareConcurrency / 2),
        },
        upscale: {
            enabled: false,
            id: "upscale",
            title: "Upscale",
            downscale: 1.0,
            models: "data/models",
            args: "",
        },
        setup: {
            enabled: false,
            id: "setup",
            title: "Setup",
            sureLimit: 0.06,
            args: "",
        },
        ocr: {
            enabled: false,
            id: "ocr",
            title: "OCR",
            credentials: "data/gcp-credentials.json",
            args: "",
        },
    }
}

const state = createState({
    busy: false,
    log: [],
    progress: 0,
    setupForms: setupFormsDefaults(),
    infoForms: {
        info: {
            alwaysEnabled: true,
            enabled: true,
            id: "info",
            title: "Info",
            titleEn: "",
            titleJp: "",
            cover: "",
            firstPage: "",
            chapterStart: 0,
            volume: 0,
        },
        chapters: {
            alwaysEnabled: true,
            enabled: true,
            id: "chapters",
            title: "Chapters",
            chapters: [],
        },
    },
    commands: [],
    tab: "setup",
    logState: "normal",
    data: null,
    pageState: {
        jp: true,
        en: false,
        blur: true,
        offset: 0,
    },
    imageFindId: null,
    imageFindValue: null,
    tooltipId: null,
    tooltipChildren: null,
    tooltipClass: null,
})

const ws = new WebSocket("ws://localhost:8080/ws")

let messageQueue = []
let messageReady = false

ws.addEventListener("open", () => {
    messageReady = true
    for (const msgStr of messageQueue) {
        ws.send(msgStr)
    }
    messageQueue = []
})

function sendMessage(msg) {
    const msgStr = JSON.stringify(msg)
    if (messageReady) {
        ws.send(msgStr)
    } else {
        messageQueue.push(msgStr)
    }
}

useEffect(() => {
    const settings = JSON.parse(JSON.stringify(state.setupForms))
    sendMessage({
        action: "settings",
        settings,
    })
})

ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data)
    if (msg.type === "log") {
        for (const typedLine of msg.log) {
            const { type, line } = typedLine
            if (type === "out") {
                const m = line.match(/<(\d+(?:\.\d+)?)%>/)
                if (m) {
                    state.progress = parseFloat(m[1]) / 100
                }
            }

            if (type === "exec-ok" || type === "exec-fail") {
                state.progress = 0
                if (state.log.length > 0) {
                    state.log[state.log.length - 1].className = `log-head--${type}`
                    if (type === "exec-ok") {
                        state.log[state.log.length - 1].show = false
                    }
                }
            }

            if (type === "exec") {
                if (state.log.length > 0) {
                    state.log[state.log.length - 1].show = false
                }
                state.log.push({ lines: [typedLine], show: true })
                state.progress = 0
            } else {
                if (state.log.length === 0) {
                    state.log.push({ lines: ["--"], show: true })
                }
                state.log[state.log.length - 1].lines.push(typedLine)
            }
        }
    } else if (msg.type === "clear-log") {
        state.log = []
    } else if (msg.type === "busy") {
        state.busy = msg.busy
    } else if (msg.type === "commands") {
        state.commands = msg.commands
    } else if (msg.type === "settings") {
        state.setupForms = msg.settings
    } else if (msg.type === "init") {
        state.data = msg.data
    }
});

function Form({ children, form }) {
    const checkboxId = `enable-${form.id}`
    const alwaysEnabled = form.alwaysEnabled ?? false
    const onEnableChange = (e) => {
        form.enabled = e.target.checked
    }
    return html`
        <div className=${{
            "form": true,
            "disabled": !form.enabled,
        }}>
            <h3 className="form-head">
                ${alwaysEnabled ? null : html`
                    <input type="checkbox"
                        checked=${form.enabled}
                        id=${checkboxId}
                        onChange=${onEnableChange} 
                        className="form-head-check" />
                `}
                <label className=${{
                    "form-head-name": true,
                    "disabled": !form.enabled,
                }} for=${checkboxId}>${form.title}</label>
            </h3>
            ${form.enabled ? html`
                <div className="form-content">
                    ${children}
                </div>
            ` : null}
        </div>
    `
}

function setTooltip(id, tooltip, tooltipClass) {
    state.tooltipId = id
    state.tooltipChildren = immutable(tooltip)
    state.tooltipClass = tooltipClass ?? "form-tooltip"
}

function clearTooltip(id) {
    if (state.tooltipId === id) {
        state.tooltipId = null
        state.tooltipChildren = null
        state.tooltipClass = null
    }
}

function InputLabel({ id, children, tooltip, className, tooltipClass }) {
    return html`
        <label
            for=${id}
            className=${className ?? "form-label"}
            onMouseover=${() => setTooltip(id, tooltip, tooltipClass)}
            onMouseout=${() => clearTooltip(id)}
        >${children}</label>
    `
}

function NumberInput({ form, prop, label, integer, min, max, children, tooltipClass }) {
    const id = `${form.id}-${prop}`
    const state = useState({
        value: form[prop].toString(),
        bad: false,
    })

    useEffect(() => {
        state.value = form[prop].toString()
        state.bad = false
    })

    const onInput = (e) => {
        const valueString = e.target.value
        state.value = valueString
        const value = valueString ? Number(valueString) : NaN
        let ok = !isNaN(value)
        if (integer !== undefined && !(Number.isSafeInteger(value))) ok = false
        if (min !== undefined && !(value >= min)) ok = false
        if (max !== undefined && !(value <= max)) ok = false
        if (ok) {
            form[prop] = value
            state.bad = false
        } else {
            state.bad = true
        }
    }

    return html`
        <div>
            <div className="form-input-parent" >
                <${InputLabel} id=${id} tooltip=${children} tooltipClass=${tooltipClass}>${label}<//>
                <input id=${id} type="text" className=${{
                        "form-input": true,
                        "bad": state.bad,
                    }} value=${state.value} onInput=${onInput} />
            </div>
        </div>
    `
}

function TextInput({ form, prop, label, children, tooltipClass, labelClass, onPaste }) {
    const id = `${form.id}-${prop}`
    const state = useState({
        value: form[prop].toString(),
        bad: false,
    })

    useEffect(() => {
        state.value = form[prop].toString()
        state.bad = false
    })

    const onInput = (e) => {
        const value = e.target.value

        let ok = true
        if (ok) {
            form[prop] = value
            state.bad = false
        } else {
            state.bad = true
        }
    }

    return html`
        <div>
            <div className="form-input-parent">
                <${InputLabel} id=${id} tooltip=${children} tooltipClass=${tooltipClass}>${label}<//>
                <input id=${id} type="text" className=${{
                        "form-input": true,
                        "bad": state.bad,
                    }} value=${state.value} onInput=${onInput} onPaste=${onPaste} />
            </div>
        </div>
    `
}

function ImageInput({ form, prop, label, children, tooltipClass, labelClass }) {
    const id = `${form.id}-${prop}`
    const local = useState({
        value: form[prop].toString(),
        bad: false,
    })

    useEffect(() => {
        local.value = form[prop].toString()
        local.bad = false
    })

    useEffect(() => {
        if (state.imageFindId === id && state.imageFindValue !== null) {
            console.log("FOUND")
            const value = state.imageFindValue
            state.imageFindId = null
            state.imageFindValue = null
            form[prop] = value
            local.value = value
            local.bad = false
        }
    })

    const onInput = (e) => {
        const value = e.target.value
        let ok = true
        if (ok) {
            form[prop] = value
            local.bad = false
        } else {
            local.bad = true
        }
    }

    const onFind = () => {
        if (state.imageFindId === id) {
            state.imageFindId = null
        } else {
            state.imageFindId = id
        }
    }

    const finding = state.imageFindId === id
    return html`
        <div>
            <div className="form-input-parent">
                <${InputLabel} className=${labelClass ?? "form-label"} id=${id} tooltip=${children} tooltipClass=${tooltipClass}>${label}<//>
                <input id=${id} type="text" className=${{
                        "form-input": true,
                        "bad": local.bad,
                    }} value=${local.value} onInput=${onInput} />
                <button onClick=${onFind} className="form-image-button">${finding ? "..." : "Select"}</button>
            </div>
        </div>
    `
}

function ArgsInput({ form, children }) {
    return html`
        <${TextInput} form=${form} prop="args" label="Arguments" tooltipClass="form-tooltip form-tooltip-args">
            <p>Extra command-line arguments passed directly.</p>
            <p>Use POSIX syntax for quoting arguments even on Windows.</p>
            ${children ? html`<table className="form-tooltip-arg-table">${children}</table>` : null}
        <//>
    `
}

function Arg({ name, children }) {
    return html`
        <tr>
            <td className="form-tooltip-arg-name">${name}</td>
            <td className="form-tooltip-arg-help">${children}</td>
        </tr>
    `
}

function SettingsForm() {
    const form = state.setupForms.settings
    return html`
        <${Form} form=${form}>
            <${NumberInput} form=${form} prop="threads" label="Thread count" integer=true min=0>
                <p>Number of threads to use for processing.</p>
                <p>Use 1 to limit into a single thread for debugging.</p>
            <//>
        <//>
    `
}

function UpscaleForm() {
    const form = state.setupForms.upscale
    return html`
        <${Form} form=${form}>
            <p className="form-info">
                Upscale source images to 2x size.
            </p>
            <${NumberInput} form=${form} prop="downscale" label="Downscale" min=0.01 max=1>
                <p>Downscale to apply after upscaling to 2x</p>
                <p>Default of 1 results in twice the size of the source image, and for example value of 0.75 results in 1.5x upscaling from the original</p>
            <//>
            <${TextInput} form=${form} prop="models" label="Models">
                <p>Path to model weights</p>
            <//>
            <${ArgsInput} form=${form}>
                <${Arg} name="--tile-size">Size of the tiles used to process<//>
            <//>
        <//>
    `
}

function SetupForm() {
    const form = state.setupForms.setup
    return html`
        <${Form} form=${form}>
            <p className="form-info">
                Optically match Japanese pages to English ones.
            </p>
            <${NumberInput} form=${form} prop="sureLimit" label="Sure limit" min=0 max=1>
                <p>Threshold for considering two images equal.</p>
                <p>When matching EN to JP pages if two consecutive pages have error less than this value no other pages are considered.</p>
                <p>Use 0 to disable and force exhaustive matching of pages.</p>
            <//>
            <${ArgsInput} form=${form}>
                <${Arg} name="--skip-resize">Use cached resized images<//>
                <${Arg} name="--error-limit value">Maximum error to accept a page<//>
                <${Arg} name="--save-match">Save temporary match images<//>
            <//>
        <//>
    `
}

function OcrForm() {
    const form = state.setupForms.ocr
    return html`
        <${Form} form=${form}>
            <p className="form-info">
                Scan text from the Japanese pages and generate page information .json files.
            </p>
            <${TextInput} form=${form} prop="credentials" label="GCP Creds">
                <p>Relative path to GCP credentials JSON file.</p>
            <//>
            <${ArgsInput} form=${form}>
                <${Arg} name="--range begin:end">Proecss a range of pages<//>
                <${Arg} name="--jdict path.json">Japanese dictionary .json<//>
                <${Arg} name="--en-dicts path">English word list files<//>
                <${Arg} name="--wanikani path.json">Wanikani subject file<//>
                <${Arg} name="--unsafe-write">Write results unsafely<//>
            <//>
        <//>
    `
}

function FormButtons() {

    const onReset = () => {
        state.setupForms = setupFormsDefaults()
    }

    const onExecute = () => {
        state.progress = 0
        sendMessage({
            action: "execute",
        })
    }

    const onCancel = () => {
        sendMessage({
            action: "cancel",
        })
    }

    return html`
        <div className="form-button-parent">
            ${!state.busy ? html`
                <button className="form-button form-execute-button" onClick=${onExecute}>
                    Execute
                </button>
            ` : html`
                <button className="form-button form-cancel-button" onClick=${onCancel}>
                    Cancel
                </button>
            `}
            <button className="form-button form-reset-button" onClick=${onReset}>
                Reset
            </button>
        </div>
    `
}

function TopForm() {
    return html`
        <div className="form-container">
            <div className="form-top">
                <${SettingsForm} />
                <${UpscaleForm} />
                <${SetupForm} />
                <${OcrForm} />
                <${FormButtons} />
            </div>
        </div>
    `
}

function CommandArg({ cmd, space }) {
    return html`
        <span className="cmd-arg">
            ${cmd.map((c, ix) => html`
                ${(space || ix > 0) ? html`<span className=${{
                    "cmd-indent": space && ix == 0,
                }}>${ix > 0 ? " " : "\u00a0"}</span>` : null}<span className=${{
                    "cmd-part": true,
                    "cmd-argpart": space && ix == 0 && c.startsWith("-"),
                    "cmd-progpart": !space && ix == 0,
                }}>${c}</span>
            `)}
        </span>
    `
}

function CommandLine({ line }) {
    return html`
        <div className="cmd-line">
            ${line.map((c, ix) => html`<${CommandArg} cmd=${c} space=${ix > 0} />`)}
        </div>
    `
}

function Commands() {
    const className = ["sidebar", "commands"]
    if (state.commands.length === 0) {
        className.push("empty")
    }
    return html`
        <div className=${className}>
            ${state.commands.map(cmd => html`<${CommandLine} line=${cmd}/>`)}
        </div>
    `
}

function LogButton({ children, target }) {
    const onClick = () => {
        state.logState = target
    }

    return html`
        <button className="log-menu-button" onClick=${onClick}>
            ${children}
        </button>
    `
}

function ProgressBar() {
    return html`
        <div className="log-menu">
            ${state.logState === "normal" ? html`
                <${LogButton} target="max">\u2912<//>
                <${LogButton} target="min">\u2913<//>
            ` : html`
                <${LogButton} target="normal">${state.logState == "min" ? "\u2912" : "\u2913"}<//>
            `}
            <div className="progress-bar">
                <div className="progress-fill" style=${({
                    width: () => `${state.progress * 100}%`,
                })}/>
            </div>
        </div>
    `
}

function LogCat({ cat, minimize }) {
    const restRef = useRef()

    const onClick = () => {
        cat.show = !cat.show
    }

    if (restRef.current) {
        queueMicrotask(() => {
            restRef.current.scrollTop = restRef.current.scrollHeight
        })
    }

    const className = ["log-head"]
    if (cat.className) {
        className.push(cat.className)
    }
    if (cat.show) {
        className.push("log-head-open")
    }
    return html`
        <${Fragment}>
            ${!minimize ? html`
                <div className=${className}><button className="log-button" onClick=${onClick}>${cat.show ? "\u2013" : "+"}</button> ${cat.lines[0].line}</div>
                ${cat.show ? html`<div ref=${restRef} className="log-rest">${cat.lines.map((line, ix) => ix > 0 ?
                    html`<div className=${`log--${line.type}`}>${line.line}</div>` : null) }</div>` : null}
            ` : html`
                <div className=${className}>${cat.lines[0].line}</div>
            `}
        <//>
    `
}

function Log() {
    const className = ["log", `log-${state.logState}`]
    if (state.logState === "min" && state.log.length > 0) {
        return html`
            <div className=${className}>
                <${ProgressBar} />
                <${LogCat} cat=${state.log[state.log.length - 1]} minimize=true />
            </div>
        `
    } else {
        return html`
            <div className=${className}>
                <${ProgressBar} />
                ${state.log.map(cat => html`<${LogCat} cat=${cat} />`)}
            </div>
        `
    }
}

function NavButton({ tab, name }) {
    const onClick = () => {
        state.tab = tab
    }

    return html`
        <button className=${{
            "nav-button": true,
            "nav-selected": state.tab === tab,
        }} onClick=${onClick}>
            ${name}
        </button>
    `
}

function Nav() {
    return html`
        <nav className="nav-main">
            <${NavButton} tab="setup" name="Setup" />
            <${NavButton} tab="info" name="Info" />
        </nav>
    `
}

function TopSetup() {
    const horizontalClass = ["horizontal", `log-${state.logState}`]
    return html`
        <div className="top">
            <${Nav} />
            <div className=${horizontalClass}>
                <${TopForm} />
                <${Commands} />
            </div>
            <${Log} />
        <//>
    `
}

function InfoForm() {
    const form = state.infoForms.info
    return html`
        <${Form} form=${form}>
            <${TextInput} form=${form} prop="titleEn" label="Title EN">
                <p>English title</p>
            <//>
            <${TextInput} form=${form} prop="titleJp" label="Title JP">
                <p>Japanese title</p>
            <//>
            <${NumberInput} form=${form} prop="volume" label="Volume" integer=true min=0>
                <p>Volume number in the series.</p>
            <//>
            <${ImageInput} form=${form} prop="cover" label="Cover">
                <p>Relative path to the cover image.</p>
            <//>
            <${ImageInput} form=${form} prop="firstPage" label="First page">
                <p>Relative path to the first page with actual content.</p>
                <p>Exclude covers and inserts for this.</p>
            <//>
            <${NumberInput} form=${form} prop="chapterStart" label="Chapter start" integer=true min=0>
                <p>Number of the first chapter contained in this volume.</p>
            <//>
        <//>
    `
}

let chapterCounter = 0
function createChapter() {
    return {
        id: `chapter-${++chapterCounter}`,
        titleEn: "",
        titleJp: "",
        page: "",
    }
}

function Chapter({ chapter, index }) {
    const form = chapter

    const onRemove = () => {
        const chaptersForm = state.infoForms.chapters
        chaptersForm.chapters = chaptersForm.chapters.filter(
            c => c.id !== chapter.id)
    }

    const labelClass = "form-label form-chapter-label"

    const onPaste = (e) => {
        const paste = (e.clipboardData ?? window.clipboardData).getData("text")
        const lines = paste.split("\n").map(l => l.trim()).filter(l => l !== "")
        if (lines.length % 2 === 0 && lines.length > 0) {
            const chapters = state.infoForms.chapters.chapters
            const baseIndex = chapters.findIndex(c => c.id === chapter.id)
            if (baseIndex >= 0) {
                e.preventDefault()

                for (let srcI = 0; srcI < lines.length / 2; srcI++) {
                    const dstI = baseIndex + srcI
                    if (dstI >= chapters.length) {
                        chapters.push(createChapter())
                    }

                    const dst = chapters[dstI]
                    dst.titleEn = lines[srcI*2 + 0]
                    dst.titleJp = lines[srcI*2 + 1]
                }
            }
        }
    }

    const chapterNumber = state.infoForms.info.chapterStart + index
    return html`
        <div className="chapter">
            <div className="chapter-head">
                <span className="chapter-head-label">Chapter ${chapterNumber}</span>
                <button className="form-chapter-remove" onClick=${onRemove}>Remove</button>
            </div>
            <${TextInput} form=${form} labelClass=${labelClass} prop="titleEn" label="Title EN" onPaste=${onPaste}>
                <p>English title</p>
            <//>
            <${TextInput} form=${form} labelClass=${labelClass} prop="titleJp" label="Title JP">
                <p>Japanese title</p>
            <//>
            <${ImageInput} form=${form} labelClass=${labelClass} prop="page" label="Page">
                <p>Page where the chapter starts.</p>
                <p>Preferably a title page if the source material contains such.</p>
            <//>
        </div>
    `
}

function ChaptersForm() {
    const form = state.infoForms.chapters

    const addChapter = () => {
        form.chapters.push(createChapter())
    }

    return html`
        <${Form} form=${form}>
            <div className="form-chapters">
                ${form.chapters.map((c,i) => html`<${Chapter} key=${c.id} chapter=${c} index=${i} />`)}
                <div className="form-chapter-add">
                    <button onClick=${addChapter}>Add</button>
                </div>
            </div>
        <//>
    `
}

function InfoFormButtons() {
    const onSave = () => {
        sendMessage({
            action: "save-info",
            info: state.infoForms,
        })
    }

    return html`
        <div className="form-button-parent">
            <button className="form-button form-save-button" onClick=${onSave}>
                Save
            </button>
        </div>
    `
}


function InfoTopForm() {
    return html`
        <div className="form-container">
            <div className="form-top form-info-top">
                <${InfoForm} />
                <${ChaptersForm} />
                <${InfoFormButtons} />
            </div>
        </div>
    `
}

function PageCheckbox({ id, label, tooltip }) {
    const nsId = `page-check-${id}`
    const onChange = (e) => {
        state.pageState[id] = e.target.checked
    }
    return html`
        <div className="page-input">
            <input type="checkbox" id=${nsId} checked=${state.pageState[id]} onChange=${onChange} />
            <label for=${nsId} className="page-input-label" title=${tooltip}>${label}</label>
        </div>
    `
}

function PageNumber({ id, label, tooltip }) {
    const nsId = `page-number-${id}`
    const onInput = (e) => {
        const value = e.target.value
        if (value.match(/^-?[0-9]+$/)) {
            state.pageState[id] = Number(e.target.value) | 0
        }
    }
    return html`
        <div className="page-input">
            <input className="page-number" type="number" id=${nsId} value=${state.pageState[id]} onInput=${onInput} />
            <label for=${nsId} className="page-input-label" title=${tooltip}>${label}</label>
        </div>
    `
}

function Page({ type, index, path }) {
    const onClick = () => {
        if (state.imageFindId !== null) {
            state.imageFindValue = `${type}/${path}`
        }
    }

    const imageClass = {
        "page-image": true,
        "page-blur": state.pageState.blur,
    }
    return html`
        <div className="page">
            <button className="page-button" onClick=${onClick}>
                <img className=${imageClass} src=${`/src-img/${type}/${path}`} loading="lazy" />
            </button>
            <a href=${`/src/${type}/${path}`} title=${`${type}/${path}`}>
                <div className="page-title">${type} ${state.pageState.offset + index}</div>
            </a>
        </div>
    `
}

function Pages() {
    return html`
        <div className="sidebar pages-top">
            <div className="pages-opts">
                <${PageCheckbox} id="jp" label="JP" tooltip="Show Japanese pages" />
                <${PageCheckbox} id="en" label="EN" tooltip="Show English pages" />
                <${PageCheckbox} id="blur" label="Blur" tooltip="Blur pages (spoiler)" />
                <${PageNumber} id="offset" label="Page offset" tooltip="Offset page numbers by a fixed value" />
            </div>
            <div className="pages">
                ${state.pageState.jp ? state.data.pagesJp.map((page, ix) => html`<${Page} path=${page} type="jp" index=${ix+1} />`) : null}
                ${state.pageState.en ? state.data.pagesEn.map((page, ix) => html`<${Page} path=${page} type="en" index=${ix+1} />`) : null}
            </div>
        </div>
    `
}

function TopInfo() {
    const horizontalClass = ["horizontal", `log-${state.logState}`]
    return html`
        <div className="top">
            <${Nav} />
            <div className=${horizontalClass}>
                <${InfoTopForm} />
                <${Pages} />
            </div>
            <${Log} />
        </div>
    `
}

function TooltipPortal() {
    if (state.tooltipId === null) return null

    const target = document.getElementById(state.tooltipId)
    if (!target) return null

    const rect = target.getBoundingClientRect()
    const x = rect.right + 8
    const y = rect.top - 8

    return html`
        <div className=${state.tooltipClass} style=${{
            left: `${x}px`,
            top: `${y}px`,
        }}>
            ${state.tooltipChildren}
        </div>
    `
}

const tabs = {
    setup: TopSetup,
    info: TopInfo,
}

function Top() {
    const Tab = tabs[state.tab]
    return html`
        <${Fragment}>
            <${TooltipPortal} />
            <${Tab} />
        <//>
    `
}

const root = document.querySelector("#kaiku-root")
render(html`<${Top}/>`, root)
