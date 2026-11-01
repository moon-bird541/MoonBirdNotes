/*
 * 富文本渲染增强（客户端）
 * ---------------------------------------------------------------------------
 * 为阅读端补上博客语法：toast-ui Viewer / 后端 rendered_html 不认识的部分。
 *   1. 数学公式：$行内$ 与 $$块级$$  → KaTeX
 *   2. 提示框：  > [!NOTE] 等 GitHub / Obsidian / VitePress 风格块引用 → 带图标的提示框
 *   3. 代码块扩展：title / 行标记 / 行号 / 折叠 / Tab 代码组 → 结构 + 交互
 *
 * 渲染是幂等的：重复调用不会重复处理已渲染过的节点，
 * 因此可以安全地在每次内容更新后调用。
 */

import renderMathInElement from "katex/dist/contrib/auto-render.mjs";
import "katex/dist/katex.min.css";

import { enhanceCodeBlocks } from "./codeBlockTools";

const KATEX_DELIMITERS = [
	{ left: "$$", right: "$$", display: true },
	{ left: "\\[", right: "\\]", display: true },
	{ left: "$", right: "$", display: false },
	{ left: "\\(", right: "\\)", display: false },
];

/**
 * 提示框类型表。canonical 决定默认文案与样式类，family 只决定配色分组。
 * 与后端 `notes/markdown_extensions.py` 的 CALLOUT_TYPES 保持一致。
 */
const CALLOUT_TYPES = {
	note: { family: "note", label: "注意", icon: "ℹ" },
	abstract: { family: "note", label: "摘要", icon: "📋" },
	info: { family: "note", label: "信息", icon: "ℹ" },
	todo: { family: "note", label: "待办", icon: "☐" },
	tip: { family: "tip", label: "提示", icon: "✦" },
	success: { family: "tip", label: "成功", icon: "✔" },
	question: { family: "tip", label: "问题", icon: "❓" },
	important: { family: "important", label: "重要", icon: "❢" },
	example: { family: "important", label: "示例", icon: "🧪" },
	warning: { family: "warning", label: "警告", icon: "⚠" },
	caution: { family: "danger", label: "小心", icon: "⛔" },
	danger: { family: "danger", label: "危险", icon: "⛔" },
	failure: { family: "danger", label: "失败", icon: "✖" },
	bug: { family: "danger", label: "缺陷", icon: "🐞" },
	quote: { family: "note", label: "引用", icon: "❝" },
};

const CALLOUT_ALIASES = {
	summary: "abstract",
	tldr: "abstract",
	hint: "tip",
	check: "success",
	done: "success",
	help: "question",
	faq: "question",
	attention: "caution",
	error: "danger",
	fail: "failure",
	missing: "failure",
	cite: "quote",
};

const MARKER_PATTERN = /^\[!([A-Za-z][\w-]*)\][ \t]*(.*?)[ \t]*$/;

const resolveCalloutType = (name = "") => {
	const key = CALLOUT_ALIASES[String(name).toLowerCase()] || String(name).toLowerCase();
	const meta = CALLOUT_TYPES[key];
	if (!meta) {
		return null;
	}
	return { canonical: key, ...meta };
};

/**
 * 找到段落里承载标记的文本节点，并把 `[!TYPE] 标题` 摘掉。
 * 标记只会出现在引用块的第一行开头，因此只看首个非空文本节点的第一行。
 * toast-ui 会把软换行渲染成 `<br>`，所以标记行之后的正文通常落在下一个文本节点里。
 */
const takeCalloutMarker = (block) => {
	const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
	let node = walker.nextNode();

	// 跳过只有空白的节点（缩进、换行）
	while (node && !node.nodeValue.trim()) {
		node = walker.nextNode();
	}
	if (!node) {
		return null;
	}

	const lines = node.nodeValue.split("\n");
	const match = (lines[0] ?? "").match(MARKER_PATTERN);
	if (!match) {
		return null;
	}

	// 标记行整行都是提示框头部，正文只会出现在后续行或下一个节点
	const rest = lines.slice(1).join("\n");
	node.nodeValue = rest;

	// 段落开头的 <br> 会留下一条空白行，摘掉标记后一并清理
	let cursor = node;
	while (cursor.nextSibling && cursor.nextSibling.nodeName === "BR") {
		cursor.nextSibling.remove();
	}
	const nextText = cursor.nextSibling;
	if (nextText?.nodeType === Node.TEXT_NODE) {
		nextText.nodeValue = nextText.nodeValue.replace(/^\n+/, "");
	}

	return { name: match[1], title: (match[2] ?? "").trim() };
};

/** 把 `> [!NOTE] 标题` 形式的块引用转成带标题的提示框 */
function renderCallouts(root) {
	const quotes = root.querySelectorAll("blockquote");

	quotes.forEach((quote) => {
		if (quote.dataset.moonbirdCallout === "done") {
			return;
		}

		const firstBlock = quote.firstElementChild;
		if (!firstBlock) {
			return;
		}

		const marker = takeCalloutMarker(firstBlock);
		if (!marker) {
			return;
		}

		const meta = resolveCalloutType(marker.name);
		if (!meta) {
			return;
		}

		// 标记摘掉后段落可能已经空了，避免留下空白行
		if (!(firstBlock.textContent ?? "").trim() && !firstBlock.querySelector("*")) {
			firstBlock.remove();
		}

		const title = document.createElement("p");
		title.className = "moonbird-callout-title";
		title.textContent = marker.title
			? `${meta.icon} ${marker.title}`
			: `${meta.icon} ${meta.label}`;
		quote.insertBefore(title, quote.firstChild);

		quote.classList.add("moonbird-callout", `moonbird-callout-${meta.family}`, `moonbird-callout-${meta.canonical}`);
		quote.dataset.moonbirdCallout = "done";
	});
}

/** 用 KaTeX 渲染公式；跳过代码块内的内容，避免误伤代码示例 */
function renderMath(root) {
	if (!root.querySelector("*")) {
		return;
	}

	try {
		renderMathInElement(root, {
			delimiters: KATEX_DELIMITERS,
			throwOnError: false,
			ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code"],
		});
	} catch (error) {
		// 公式渲染失败不应影响正文阅读
		console.warn("[blog-prose] 数学公式渲染失败：", error);
	}
}

/**
 * 对容器内的富文本做一次增强渲染。
 * @param {HTMLElement | null | undefined} root
 */
export function enhanceRichContent(root) {
	if (!root) {
		return;
	}

	renderCallouts(root);
	enhanceCodeBlocks(root);
	renderMath(root);
}
