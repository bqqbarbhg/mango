
const { h, render, Component } = preact

class Result extends Component {

    render({ result, expand }) {

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
            if (glossText.length + gloss.length >= maxGloss && !expand) break
            if (glossText != "") glossText += ", "
            glossText += gloss
        }

        let conjText = result.conjugation

        return h("div", { class: "hint-container" }, [
            h("div", { class: "hint-title" }, titleText),
            h("div", { class: "hint-gloss" }, glossText),
            conjText != "" ? h("div", { class: "hint-conjugation" }, conjText) : null,
        ])
    }
}

class Hint extends Component {
    render({ hint }) {
        return h("div", {class: "top-scroll" },
            h("div", null, hint.results.map(r => h(Result, { result: r }, null)))
        )
    }
}

class Translation extends Component {
    render({ text }) {
        return h("div", {class: "top-scroll" },
            h("div", { class: "translation" }, text),
        )
    }
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

class Top extends Component {
    state = { page: null, hint: null, hintId: 0, translation: "" }
    loadToken = 0

    clickTime = 0

    componentDidMount() {
        pageImage.addEventListener("click", this.onImageClick)
        this.loadPage({ image: "data/page2.jpg", meta: "data/page2.json" })
    }

    componentWillUnmount() {
        pageImage.removeEventListener("click", this.onImageClick)
    }

    onImageClick = (e) => {
        const { page } = this.state
        if (!page) return

        let time = new Date().getTime()
        let doubleClick = (time - this.clickTime < 200)
        this.clickTime = time

        const pos = {
            x: e.offsetX,
            y: e.offsetY,
        }

        let bestDist = 20.0*20.0
        let bestHint = null
        let bestTarget = null
        let bestPara = null
        let bestCluster = null

        let paraIndex = 0
        for (const para of page.paragraphs) {
            let symIndex = 0
            for (const sym of para.symbols) {
                let dist = aabbDist(sym.aabb, pos)
                if (dist < bestDist) {
                    let foundHint = null
                    let useSymbol = false

                    if (doubleClick) {
                            bestDist = dist
                            bestPara = para
                            useSymbol = true
                            for (const cluster of page.clusters) {
                                if (cluster.paragraphs.includes(paraIndex)) {
                                    bestCluster = cluster
                                    break
                                }
                            }
                            bestTarget = {
                                x: (bestCluster.aabb.min[0] + bestCluster.aabb.max[0]) * 0.5,
                                y: (bestCluster.aabb.min[1] + bestCluster.aabb.max[1]) * 0.5,
                                width: bestCluster.aabb.max[0] - bestCluster.aabb.min[0],
                                visible: true,
                            }
                    } else {
                        for (const hint of para.hints) {
                            if (symIndex >= hint.begin && symIndex < hint.end) {
                                foundHint = hint
                                break
                            }
                        }

                        if (foundHint) {
                            bestTarget = {
                                x: (sym.aabb.min[0] + sym.aabb.max[0]) * 0.5,
                                y: (sym.aabb.min[1] + sym.aabb.max[1]) * 0.5,
                                width: sym.aabb.max[0] - sym.aabb.min[0],
                                visible: true,
                            }
                            bestDist = dist
                            bestHint = foundHint
                            bestPara = para
                        }
                    }
                }
                symIndex += 1
            }
            paraIndex += 1
        }

        let translation = ""

        if (!doubleClick && bestHint) {
            let rects = []
            for (let i = bestHint.begin; i < bestHint.end; i++) {
                const sym = bestPara.symbols[i]
                rects.push(sym.aabb)
            }
            updateHighlights(rects)

            rootTarget = bestTarget
            updateRoot()
        } else if (doubleClick && bestCluster) {

            let rects = []
            for (const paraIx of bestCluster.paragraphs) {
                for (const sym of page.paragraphs[paraIx].symbols) {
                    rects.push(sym.aabb)
                }
            }
            updateHighlights(rects)
            translation = bestCluster.translation

            rootTarget = bestTarget
            updateRoot()

        } else if (rootTarget.visible) {
            rootTarget.visible = false
            updateRoot()
            updateHighlights([])
        }

        this.setState({
            hint: bestHint,
            hintId: (this.state.hintId + 1) % 4096,
            translation: translation,
        })
    }

    loadPage(page) {
        pageImage.src = page.image

        const token = ++this.loadToken
        fetch(page.meta)
            .then(r => r.json())
            .then(page => this.onLoadMetadata(page, token))
    }

    onLoadMetadata(page, token) {
        if (token != this.loadToken) return

        this.setState({ page: page })
    }

    render({ }, { hint, hintId, translation }) {

        return h("div", { class: "top" }, [
            hint ? h(Hint, { hint: hint, key: hintId }) : null,
            translation != "" ? h(Translation, { text: translation }) : null,
        ])
    }
}

const highlightRoot = document.getElementById("highlight-root")
const preactRoot = document.getElementById("preact-root")

let highlightElems = []

let rootPos = { x: 0, y: 0 }
let rootSize = { x: 0, y: 0 }
let rootVisible = false
let rootFontSize = 0

let updateRootInterval = 0
let rootUpdatesLeft = 0

let rootOnRight = false

function updateHighlights(rects) {
    for (const elem of highlightElems) {
        highlightRoot.removeChild(elem)
    }

    highlightElems = []

    for (const rect of rects) {
        const elem = document.createElement("div")

        let centerX = (rect.min[0] + rect.max[0]) * 0.5
        let centerY = (rect.min[1] + rect.max[1]) * 0.5
        let extentX = (rect.max[0] - rect.min[0]) * 0.5
        let extentY = (rect.max[1] - rect.min[1]) * 0.5

        extentX *= 1.3;
        extentY *= 1.3;

        if (extentY < extentX) {
            extentY = extentX
        }

        elem.style.position = "absolute"
        elem.style.left = `${centerX - extentX}px`
        elem.style.top = `${centerY - extentY}px`
        elem.style.width = `${extentX * 2}px`
        elem.style.height = `${extentY * 2}px`
        elem.className = "highlighter"

        highlightRoot.appendChild(elem)
        highlightElems.push(elem)
    }
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
            x: rootTarget.x - elemSize.x - rootTarget.width,
            y: rootTarget.y - elemSize.y * 0.5,
        }
    } else {
        targetPos = {
            x: rootTarget.x + rootTarget.width,
            y: rootTarget.y - elemSize.y * 0.5,
        }
    }

    const pos = v2clamp(targetPos, minPos, maxPos)

    const deltaX = (rootPos.x - pos.x) / viewSize.x
    const deltaY = (rootPos.y - pos.y) / viewSize.y
    const minDelta = 0.00001

    const sizeDeltaX = (rootSize.x - elemSize.x) / viewSize.x
    const sizeDeltaY = (rootSize.y - elemSize.y) / viewSize.y
    const minSizeDelta = 0.00001

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

    if (--rootUpdatesLeft == 0) {
        clearInterval(updateRootInterval)
        updateRootInterval = 0
    }
}

function updateRoot()
{
    rootUpdatesLeft = 100
    if (updateRootInterval == 0) {
        updateRootImp()
        updateRootInterval = setInterval(updateRootImp, 10)
    }
}

window.addEventListener("touchmove", updateRoot)
window.addEventListener("scroll", updateRoot)
new ResizeObserver(updateRoot).observe(preactRoot)
updateRoot()

render(h(Top), preactRoot)
