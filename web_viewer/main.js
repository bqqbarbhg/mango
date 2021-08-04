
const { h, render, Component, createRef } = preact
const { h: k, render: kaikuRender, createState, useState } = kaiku

function Radical({ radical }) {
    return k("div", { className: "radical" },
        k("img", { className: "radical-image", src: radical.image }),
        k("div", { className: "radical-text" }, radical.name)
    )
}

function RadicalList({ radicals }) {
    return k("div", { className: "radical-list" },
        radicals.map(r => k(Radical, { radical: r }))
    )
}

function Result({ hintSelectionState, result, key }) {
    const index = key
    const expand = hintSelectionState.selectedIndex == index

    let titleText = ""

    if (result.kanji.length > 0) {
        titleText += result.kanji[0].text
    }

    if (result.kana.length > 0) {
        if (titleText != "") {
            titleText += "【" + result.kana[0].text + "】"
        } else {
            titleText += result.kana[0].text;
        }
    }

    let glossText = ""
    let maxGloss = 50

    for (const gloss of result.gloss) {
        if (glossText && glossText.length + gloss.length >= maxGloss && !expand) break
        if (glossText != "") glossText += ", "
        glossText += gloss
    }

    let kanjiText = ""
    let kanaText = ""

    let wkPart = []

    if (expand) {
        for (const kanji of result.kanji) {
            if (kanjiText) kanjiText += ", "
            kanjiText += kanji.text
        }

        for (const kana of result.kana) {
            if (kanaText) kanaText += ", "
            kanaText += kana.text
        }

        const wkLists = [
            result.wk_meaning_mnemonic,
            result.wk_meaning_hint,
            result.wk_reading_mnemonic,
            result.wk_reading_hint,
        ]

        for (const list of wkLists) {
            if (!list) continue

            wkPart.push(k("div", { class: "wk-container" },
                list.map(({ type, text }) => k("span", { class: `wk-span wk-tag-${type}` }, text))))
        }
    }

    let conjText = result.conjugation

    return k("div", {
        className: {
            "hint-container": true,
            "hint-selected": expand,
        },
        onClick: () => { hintSelectionState.selectedIndex = index },
    }, [
        k("div", { className: "hint-title" }, titleText),
        result.radicals ? k(RadicalList, { radicals: result.radicals }) : null,
        k("div", { className: "hint-gloss" }, glossText),
        conjText ? k("div", { className: "hint-conjugation" }, conjText) : null,
        kanjiText ? k("div", null,
            k("span", { className: "hint-label" }, "Writing: "),
            k("span", { className: "hint-text" }, kanjiText)) : null,
        kanaText ? k("div", null,
            k("span", { className: "hint-label" }, "Reading: "),
            k("span", { className: "hint-text" }, kanaText)) : null,
        wkPart
    ])
}

function Hint({ hint }) {
    const hintSelectionState = useState({ selectedIndex: -1 })
    return k("div", {className: "top-scroll" },
        k("div", null, hint.results.map((r, ix) =>
            k(Result, {
                hintSelectionState,
                result: r,
                key: ix }, null))))
}

function Translation({ text }) {
    return k("div", {className: "top-scroll" },
        k("div", { className: "translation" }, text),
    )
}

const pageImage = document.getElementById("page-image")

function aabbDist(aabb, pos) {
    const cx = Math.min(Math.max(pos.x, aabb.min[0]), aabb.max[0])
    const cy = Math.min(Math.max(pos.y, aabb.min[1]), aabb.max[1])
    const dx = pos.x - cx
    const dy = pos.y - cy
    return dx*dx + dy*dy
}

let rootTarget = { x: 0, y: 0, width: 0, visible: false }

function getNearestSymbol(page, pos, distance=20.0) {
    let bestDist = distance*distance
    let bestParaIndex = -1
    let bestSymIndex = -1
    let paraIndex = 0
    for (const para of page.paragraphs) {
        let symIndex = 0
        for (const sym of para.symbols) {
            let dist = aabbDist(sym.aabb, pos)
            if (dist < bestDist) {
                bestParaIndex = paraIndex
                bestSymIndex = symIndex
                bestDist = dist
            }
            symIndex += 1
        }
        paraIndex += 1
    }

    if (bestParaIndex < 0) return null
    return { paraIx: bestParaIndex, symIx: bestSymIndex, distance: Math.sqrt(bestDist) }
}

function getCluster(page, paraIx) {
    for (const cluster of page.clusters) {
        if (cluster.paragraphs.includes(paraIx)) {
            return cluster
        }
    }
}

function getHint(paragraph, symIx) {
    for (const hint of paragraph.hints) {
        if (symIx >= hint.begin && symIx < hint.end) {
            return hint
        }
    }
    return null
}

function getAltHint(paragraph, symBegin, symEnd) {
    for (const hint of paragraph.alt_hints) {
        if (symBegin == hint.begin && symEnd == hint.end) {
            return hint
        }
    }
    return null
}

function getClusterRects(page, cluster) {
    let rects = []
    for (const paraIx of cluster.paragraphs) {
        for (const sym of page.paragraphs[paraIx].symbols) {
            rects.push(sym.aabb)
        }
    }
    return rects
}

function getSelectionRects(page, selection) {
    let rects = []
    const paragraph = page.paragraphs[selection.paraIx]
    for (let i = selection.symBegin; i < selection.symEnd; i++) {
        const sym = paragraph.symbols[i]
        rects.push(sym.aabb)
    }
    return rects
}

function getSelectionTarget(page, selection) {
    const paragraph = page.paragraphs[selection.paraIx]
    let minX = +Infinity
    let maxX = -Infinity
    let minY = +Infinity
    let maxY = -Infinity
    for (let i = selection.symBegin; i < selection.symEnd; i++) {
        const aabb = paragraph.symbols[i].aabb
        minX = Math.min(minX, aabb.min[0])
        maxX = Math.max(maxX, aabb.max[0])
        minY = Math.min(minY, aabb.min[1])
        maxY = Math.max(maxY, aabb.max[1])
    }
    return {
        x: (minX + maxX) * 0.5,
        y: (minY + maxY) * 0.5,
        width: (maxX - minX) * 0.5,
        visible: true,
    }
}

function KaikuTop({ state }) {
    return k("div", { className: "top" }, [
        state.hint ? k(Hint, { hint: state.hint, key: state.hintId }) : null,
        state.translation != "" ? k(Translation, { text: state.translation }) : null,
    ])
}

class Top {
    state = null
    loadToken = 0
    currentPage = 0
    clickTime = 0
    preloadImage = new Image()
    lastGoodPage = null
    selection = null
    dragSelection = null
    dragSelectionBegin = false
    dragSelectionEnd = false
    skipClick = false
    dragTouchId = null
    dragTapSymbolIx = -1

    constructor() {
        const params = new URLSearchParams(window.location.search)
        this.doc = params.get("doc")
        this.state = createState({ page: null, hint: null, hintId: 0, translation: "" })

        pageImage.addEventListener("mousedown", this.onImageMouseDown)
        pageImage.addEventListener("mousemove", this.onImageMouseMove)
        pageImage.addEventListener("mouseup", this.onImageMouseUp)
        window.addEventListener("touchstart", this.onImageTouchStart, { passive: false })
        window.addEventListener("touchmove", this.onImageTouchMove, { passive: false })
        window.addEventListener("touchend", this.onImageTouchEnd, { passive: false })
        window.addEventListener("touchcancel", this.onImageTouchEnd, { passive: false })
        pageImage.addEventListener("click", this.onImageClick)
        window.addEventListener("hashchange", this.onHashChange)

        let page = parseInt(window.location.hash.substring(1))
        if (isNaN(page)) page = 1
        this.loadPageIndex(page)
    }

    setState(patch) {
        for (const key in patch) {
            this.state[key] = patch[key]
        }
    }

    componentWillUnmount() {
        pageImage.removeEventListener("mousedown", this.onImageMouseDown)
        pageImage.removeEventListener("mousemove", this.onImageMouseMove)
        pageImage.removeEventListener("mouseup", this.onImageMouseUp)
        window.removeEventListener("touchstart", this.onImageTouchStart)
        window.removeEventListener("touchmove", this.onImageTouchMove)
        window.removeEventListener("touchend", this.onImageTouchEnd)
        window.removeEventListener("touchcancel", this.onImageTouchEnd)
        pageImage.removeEventListener("click", this.onImageClick)
        window.removeEventListener("hashchange", this.onHashChange)
    }

    onHashChange = (e) => {
        let page = parseInt(window.location.hash.substring(1))
        if (isNaN(page)) page = 1
        this.loadPageIndex(page)
    }

    onImageClick = (e) => {
        if (this.skipClick) {
            this.skipClick = false
            return
        }

        const { page } = this.state
        if (!page) return

        let time = new Date().getTime()
        let doubleClick = (time - this.clickTime < 200)
        this.clickTime = time

        const pos = {
            x: e.offsetX,
            y: e.offsetY,
        }

        const hit = getNearestSymbol(page, pos)

        if (hit) {
            if (doubleClick) {
                const cluster = getCluster(page, hit.paraIx)
                updateHighlights(getClusterRects(page, cluster))
                this.selection = null
                this.dragSelection = null

                rootTarget = {
                    x: (cluster.aabb.min[0] + cluster.aabb.max[0]) * 0.5,
                    y: (cluster.aabb.min[1] + cluster.aabb.max[1]) * 0.5,
                    width: (cluster.aabb.max[0] - cluster.aabb.min[0]) * 0.5,
                    visible: true,
                }

                this.setState({
                    hint: null,
                    hintId: (this.state.hintId + 1) % 4096,
                    translation: cluster.translation,
                })
            } else {
                const hint = getHint(page.paragraphs[hit.paraIx], hit.symIx)

                if (hint) {
                    this.selection = {
                        paraIx: hit.paraIx,
                        symBegin: hint.begin,
                        symEnd: hint.end,
                    }
                    updateHighlights(getSelectionRects(page, this.selection))
                    rootTarget = getSelectionTarget(page, this.selection)
                    this.setState({
                        hint: hint,
                        hintId: (this.state.hintId + 1) % 4096,
                        translation: "",
                    })
                } else {
                    this.selection = {
                        paraIx: hit.paraIx,
                        symBegin: hit.symIx,
                        symEnd: hit.symIx + 1,
                    }
                    updateHighlights(getSelectionRects(page, this.selection))
                    rootTarget = getSelectionTarget(page, this.selection)
                    this.setState({
                        hint: null,
                        hintId: (this.state.hintId + 1) % 4096,
                        translation: "???",
                    })
                }
            }
        } else {
            this.selection = null
            rootTarget.visible = false
            updateHighlights([])

            if (doubleClick) {
                const width = pageImage.clientWidth

                if (pos.x < width * 0.25) {
                    if (this.currentPage > 1) {
                        this.loadPageIndex(this.currentPage - 1)
                    }
                } else if (pos.x > width * 0.75) {
                    this.loadPageIndex(this.currentPage + 1)
                }
            }

        }
        updateRoot()
    }

    dragStart(pos) {
        const { page } = this.state
        if (!page) return false

        let time = new Date().getTime()
        let doubleClick = (time - this.clickTime < 200)
        if (doubleClick) return false

        if (this.selection) {
            const hit = getNearestSymbol(page, pos)
            if (hit && hit.paraIx == this.selection.paraIx
                    && hit.symIx >= this.selection.symBegin
                    && hit.symIx < this.selection.symEnd) {
                if (this.selection.symEnd - this.selection.symBegin <= 3) {
                    this.dragSelectionBegin = hit.symIx == this.selection.symBegin
                    this.dragSelectionEnd = hit.symIx == this.selection.symEnd - 1
                } else {
                    this.dragSelectionBegin = hit.symIx <= this.selection.symBegin + 1
                    this.dragSelectionEnd = hit.symIx >= this.selection.symEnd - 2
                }
                if (this.dragSelectionBegin || this.dragSelectionEnd) {
                    this.dragSelection = this.selection
                }
                this.dragTapSymbolIx = hit.symIx
                return true
            }
        }

        return false
    }

    dragMove(pos) {
        const { page } = this.state
        if (!page) return
        if (!this.dragSelection) return

        const hit = getNearestSymbol(page, pos)
        if (!hit) {
            this.dragTapSymbolIx = -1
        }

        if (hit && hit.paraIx == this.dragSelection.paraIx) {
            const prevSelection = this.selection
            if (this.dragSelectionBegin && this.dragSelectionEnd) {
                this.selection = {
                    paraIx: this.dragSelection.paraIx,
                    symBegin: Math.min(hit.symIx, this.dragSelection.symBegin),
                    symEnd: Math.max(hit.symIx + 1, this.dragSelection.symEnd),
                }
            } else if (this.dragSelectionBegin) {
                this.selection = {
                    paraIx: this.dragSelection.paraIx,
                    symBegin: Math.min(hit.symIx, this.dragSelection.symEnd - 1),
                    symEnd: this.dragSelection.symEnd,
                }
            } else if (this.dragSelectionEnd) {
                this.selection = {
                    paraIx: this.dragSelection.paraIx,
                    symBegin: this.dragSelection.symBegin,
                    symEnd: Math.max(hit.symIx + 1, this.dragSelection.symBegin + 1),
                }
            }

            if (this.selection.symBegin != prevSelection.symBegin || this.selection.symEnd != prevSelection.symEnd) {
                this.dragTapSymbolIx = -1
                const hint = getAltHint(page.paragraphs[hit.paraIx], this.selection.symBegin, this.selection.symEnd)

                if (hint != this.state.hint) {
                    this.setState({
                        hint: hint,
                        hintId: (this.state.hintId + 1) % 4096,
                        translation: "",
                    })
                }

                rootTarget = getSelectionTarget(page, this.selection)
                updateHighlights(getSelectionRects(page, this.selection))
                updateRoot()
            }
        } else {
            this.selection = this.dragSelection
        }
    }

    dragEnd() {
        const { page } = this.state

        if (page && this.selection && this.dragTapSymbolIx >= 0) {
            const symIx = this.dragTapSymbolIx
            this.dragTapSymbolIx = -1

            this.selection = {
                paraIx: this.selection.paraIx,
                symBegin: symIx,
                symEnd: symIx + 1,
            }

            const hint = getAltHint(page.paragraphs[this.selection.paraIx], symIx, symIx + 1)
            if (hint != this.state.hint) {
                this.setState({
                    hint: hint,
                    hintId: (this.state.hintId + 1) % 4096,
                    translation: "",
                })
            }

            rootTarget = getSelectionTarget(page, this.selection)
            updateHighlights(getSelectionRects(page, this.selection))
            updateRoot()
        }

        if (this.dragSelection != null) {
            this.clickTime = new Date().getTime()
        }
        this.dragSelection = null
    }

    onImageMouseDown = (e) => {
        if (e.button != 0) return

        if (this.dragStart({ x: e.offsetX, y: e.offsetY })) {
            this.skipClick = true
            e.preventDefault()
            return false
        }
    }

    onImageMouseMove = (e) => {
        if ((e.buttons & 1) == 0) {
            this.dragSelection = null
            return
        }

        this.dragMove({ x: e.offsetX, y: e.offsetY })
        e.preventDefault()
        return false
    }

    onImageMouseUp = (e) => {
        const { page } = this.state
        if (!page) return
        if ((e.buttons & 1) != 0) return

        this.dragEnd()
        e.preventDefault()
        return false
    }

    hackcount = 0

    onImageTouchStart = (e) => {
        if (this.dragTouchId !== null) return

        for (let touch of e.changedTouches) {
            if (this.dragStart({ x: touch.pageX, y: touch.pageY })) {
                this.dragTouchId = touch.identifier
                e.preventDefault()
                return false
            }
        }
    }

    onImageTouchMove = (e) => {
        for (let touch of e.changedTouches) {
            if (touch.identifier === this.dragTouchId) {
                this.dragMove({ x: touch.pageX, y: touch.pageY })
                e.preventDefault()
                return false
            }
        }
    }

    onImageTouchEnd = (e) => {
        for (let touch of e.changedTouches) {
            if (touch.identifier === this.dragTouchId) {
                this.dragTouchId = null
                this.dragEnd()
                e.preventDefault()
                return false
            }
        }
    }

    loadPageIndex(pageIndex) {
        pageIndex = pageIndex | 0
        if (this.currentPage == pageIndex) return
        this.currentPage = pageIndex

        history.pushState(null, null, "#" + pageIndex.toString());

        let indexStr = pageIndex.toString().padStart(3, "0")
        let baseName = `${this.doc}/page${indexStr}`
        this.loadPageImp({ image: baseName + ".jpg", meta: baseName + ".json", index: pageIndex })
    }

    loadPageImp(pageInfo) {
        pageImage.src = pageInfo.image

        this.setState({ page: null })
        this.selection = null
        this.dragSelection = null

        const token = ++this.loadToken
        fetch(pageInfo.meta)
            .then(r => r.json())
            .then(page => this.onLoadMetadata(page, token, pageInfo))
            .catch(error => this.onLoadError(error))
    }

    onLoadError(error) {
        if (this.lastGoodPage) {
            this.loadPageIndex(this.lastGoodPage.index)
        }
    }

    onLoadMetadata(page, token, pageInfo) {
        if (token != this.loadToken) return

        // Preload the next image
        {
            let indexStr = (pageInfo.index + 1).toString().padStart(3, "0")
            this.preloadImage.src = `${this.doc}/page${indexStr}.jpg`
        }

        this.lastGoodPage = pageInfo
        this.setState({ page: page })
    }

    mount(root) {
        kaikuRender(k(KaikuTop, { state: this.state }), root, this.state)
    }
}

const highlightRoot = document.getElementById("highlight-root")
const preactRoot = document.getElementById("preact-root")

function HighlightRect({ rect })
{
    let centerX = (rect.min[0] + rect.max[0]) * 0.5
    let centerY = (rect.min[1] + rect.max[1]) * 0.5
    let extentX = (rect.max[0] - rect.min[0]) * 0.5
    let extentY = (rect.max[1] - rect.min[1]) * 0.5

    extentX *= 1.3;
    extentY *= 1.3;

    extentY = extentX = Math.max(extentX, extentY)

    return k("div", {
        className: "highlighter",
        style: {
            position: "absolute",
            left: `${centerX - extentX}px`,
            top: `${centerY - extentY}px`,
            width: `${extentX * 2}px`,
            height: `${extentY * 2}px`,
        },
    })
}

function HighlightTop()
{
    return k("div", { }, highlightState.rects.map(rect => k(HighlightRect, { rect })))
}

const highlightState = createState({ rects: [] })
kaikuRender(k(HighlightTop), highlightRoot, highlightState)

let rootPos = { x: 0, y: 0 }
let rootSize = { x: 0, y: 0 }
let rootVisible = false
let rootFontSize = 0

let rootUpdatesLeft = 0

let rootOnRight = false

function updateHighlights(rects) {
    highlightState.rects = rects
}

function v2clamp(a, min, max) {
    return {
        x: Math.min(Math.max(a.x, min.x), max.x),
        y: Math.min(Math.max(a.y, min.y), max.y),
    }
}

function v2mul(a, b) {
    return { x: a.x * b.x, y: a.y * b.y }
}

function v2addmuls(a, b, c) {
    return { x: a.x + b.x * c, y: a.y + b.y * c }
}

function v2addmul(a, b, c) {
    return { x: a.x + b.x * c.x, y: a.y + b.y * c.y }
}

function updateRootImp()
{
    const bodyRect = document.body.getBoundingClientRect()
    const viewOffset = { x: -bodyRect.x, y: -bodyRect.y }
    const viewSize = { x: window.innerWidth, y: window.innerHeight }

    const elemViewSize = { x: 0.45, y: 0.3 }
    const elemSize = v2mul(elemViewSize, viewSize)

    const minPos = v2addmuls(viewOffset, viewSize, 0.02)
    const maxPos = v2addmul(viewOffset, viewSize, {
        x: 0.98 - elemViewSize.x,
        y: 0.98 - elemViewSize.y,
    })

    if (!rootOnRight && rootTarget.x > minPos.x + viewSize.x * 0.52) {
        rootOnRight = true
    } else if (rootOnRight && rootTarget.x < minPos.x + viewSize.x * 0.48) {
        rootOnRight = false
    }

    if (rootVisible != rootTarget.visible) {
        rootVisible = rootTarget.visible
        preactRoot.style.display = rootTarget.visible ? "block" : "none";
    }

    let targetPos
    if (rootOnRight) {
        targetPos = {
            x: rootTarget.x - elemSize.x * 1.05 - rootTarget.width,
            y: rootTarget.y - elemSize.y * 0.5,
        }
    } else {
        targetPos = {
            x: rootTarget.x + rootTarget.width + elemSize.x * 0.05,
            y: rootTarget.y - elemSize.y * 0.5,
        }
    }

    const pos = v2clamp(targetPos, minPos, maxPos)

    const deltaX = (rootPos.x - pos.x) / viewSize.x
    const deltaY = (rootPos.y - pos.y) / viewSize.y
    const minDelta = 0.0000001

    const sizeDeltaX = (rootSize.x - elemSize.x) / viewSize.x
    const sizeDeltaY = (rootSize.y - elemSize.y) / viewSize.y
    const minSizeDelta = 0.001

    if (sizeDeltaX*sizeDeltaX + sizeDeltaY*sizeDeltaY > minSizeDelta*minSizeDelta) {
        rootSize.x = elemSize.x
        rootSize.y = elemSize.y
        const fontSize = (elemSize.y / 14.0);
        if (Math.abs(rootFontSize - fontSize) > 1.0) {
            rootFontSize = fontSize | 0
            preactRoot.style.fontSize = `${rootFontSize}px`
        }

        preactRoot.style.width = `${elemSize.x}px`
        preactRoot.style.height = `${elemSize.y}px`
    }

    if (deltaX*deltaX + deltaY*deltaY > minDelta*minDelta) {
        rootPos.x = pos.x
        rootPos.y = pos.y
        preactRoot.style.transform = `translate(${pos.x}px, ${pos.y}px)`
    }

    if (--rootUpdatesLeft > 0) {
        window.requestAnimationFrame(updateRootImp)
        updateRootInterval = 0
    }
}

function updateRoot()
{
    if (rootUpdatesLeft == 0) {
        rootUpdatesLeft = 100
        updateRootImp()
    } else {
        rootUpdatesLeft = 100
    }
}

window.addEventListener("touchmove", updateRoot)
window.addEventListener("scroll", updateRoot)
new ResizeObserver(updateRoot).observe(preactRoot)
updateRoot()

// render(h(Top), preactRoot)
new Top().mount(preactRoot)
