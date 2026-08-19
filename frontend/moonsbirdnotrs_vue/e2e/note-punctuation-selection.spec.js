import { expect, test } from '@playwright/test'

const currentUser = {
  id: 1,
  username: 'punctuation-tester',
}

const fulfillJson = (route, status, body) =>
  route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })

const mockNoteEditorApi = async (page, markdownContent = '\u4f60\u597d') => {
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname

    if (path === '/api/session/') {
      return fulfillJson(route, 200, { user: currentUser })
    }

    if (path === '/api/notes/1/') {
      return fulfillJson(route, 200, {
        id: 1,
        title: 'Punctuation regression',
        tags: [],
        markdown_content: markdownContent,
        rendered_html: '',
        created_at: '2026-08-16T00:00:00Z',
        updated_at: '2026-08-16T00:00:00Z',
      })
    }

    if (path === '/api/notes/tags/' || path === '/api/notes/1/versions/') {
      return fulfillJson(route, 200, [])
    }

    return fulfillJson(route, 404, { detail: `Unhandled note editor API: ${request.method()} ${path}` })
  })
}

const getEditorSelection = (editor) =>
  editor.evaluate(() => {
    const selection = document.getSelection()
    return {
      collapsed: selection?.isCollapsed ?? true,
      text: selection?.toString() || '',
    }
  })

const waitForEditorBindings = (editor) =>
  editor.evaluate(
    () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  )

const emulatePunctuationSelectionBug = (editor, { punctuation, eventType, reverseSelection = false }) =>
  editor.evaluate(
    (root, input) => {
      const selection = document.getSelection()
      const textNode = selection?.focusNode
      const endOffset = selection?.focusOffset

      if (
        !selection?.isCollapsed ||
        textNode?.nodeType !== Node.TEXT_NODE ||
        textNode.textContent.slice(endOffset - input.punctuation.length, endOffset) !== input.punctuation
      ) {
        throw new Error('The inserted punctuation is not immediately before the caret')
      }

      const range = document.createRange()
      range.setStart(textNode, endOffset - input.punctuation.length)
      range.setEnd(textNode, endOffset)
      selection.removeAllRanges()
      if (input.reverseSelection && typeof selection.setBaseAndExtent === 'function') {
        selection.setBaseAndExtent(
          textNode,
          endOffset,
          textNode,
          endOffset - input.punctuation.length
        )
      } else {
        selection.addRange(range)
      }

      const event =
        input.eventType === 'compositionend'
          ? new CompositionEvent('compositionend', { bubbles: true, data: input.punctuation })
          : new InputEvent('input', {
              bubbles: true,
              data: input.punctuation,
              inputType: 'insertText',
            })
      root.dispatchEvent(event)
    },
    { punctuation, eventType, reverseSelection }
  )

const selectEditorPrefix = (editor, length) =>
  editor.evaluate((root, prefixLength) => {
    const textNode = root.querySelector('p')?.firstChild
    const range = document.createRange()
    range.setStart(textNode, 0)
    range.setEnd(textNode, prefixLength)
    const selection = document.getSelection()
    selection.removeAllRanges()
    selection.addRange(range)
  }, length)

const pageErrors = new WeakMap()

test.beforeEach(async ({ page }) => {
  const errors = []
  pageErrors.set(page, errors)
  page.on('pageerror', (error) => errors.push(error.message))
})

test.afterEach(async ({ page }) => {
  expect(pageErrors.get(page)).toEqual([])
})

test('punctuation input collapses an anomalous selection before the next character', async ({ page }) => {
  await mockNoteEditorApi(page)
  await page.goto('/notes/1/edit')

  const editor = page.locator('.toastui-editor-ww-container .ProseMirror')
  await editor.click()
  await waitForEditorBindings(editor)
  await page.keyboard.press('Control+End')

  const punctuationCases = [
    ...'\uff0c\u3002\uff01\uff1f\uff1b\uff1a'.split('').map((punctuation, index) => ({
      punctuation,
      eventType: 'compositionend',
      followingText: index === 0 ? '\u4e16\u754c' : index === 1 ? '\ud83d\ude42' : '\u4e2d',
      reverseSelection: index === 0,
    })),
    ...',.!?;:'.split('').map((punctuation) => ({
      punctuation,
      eventType: 'input',
      followingText: 'x',
    })),
  ]
  let expectedText = '\u4f60\u597d'

  for (const punctuationCase of punctuationCases) {
    await page.keyboard.insertText(punctuationCase.punctuation)
    await emulatePunctuationSelectionBug(editor, punctuationCase)
    await expect.poll(() => getEditorSelection(editor)).toEqual({ collapsed: true, text: '' })
    await page.keyboard.insertText(punctuationCase.followingText)
    expectedText += punctuationCase.punctuation + punctuationCase.followingText
    await expect(editor).toHaveText(expectedText)
  }
})

test('a deliberate editor selection remains non-empty without text input', async ({ page }) => {
  await mockNoteEditorApi(page)
  await page.goto('/notes/1/edit')

  const editor = page.locator('.toastui-editor-ww-container .ProseMirror')
  await editor.click()
  await waitForEditorBindings(editor)
  await selectEditorPrefix(editor, 1)

  await expect.poll(() => getEditorSelection(editor)).toEqual({
    collapsed: false,
    text: '\u4f60',
  })
  await expect(page.locator('.floating-toolbar')).toBeVisible()
})

test('punctuation in an embedded editor input does not collapse a document selection', async ({ page }) => {
  await mockNoteEditorApi(page, ';')
  await page.goto('/notes/1/edit')

  const editor = page.locator('.toastui-editor-ww-container .ProseMirror')
  await editor.click()
  await waitForEditorBindings(editor)
  await selectEditorPrefix(editor, 1)

  await editor.evaluate((root) => {
    const input = document.createElement('input')
    input.setAttribute('contenteditable', 'false')
    root.appendChild(input)
    input.dispatchEvent(
      new InputEvent('input', {
        bubbles: true,
        data: ';',
        inputType: 'insertText',
      })
    )
  })
  await waitForEditorBindings(editor)

  await expect.poll(() => getEditorSelection(editor)).toEqual({
    collapsed: false,
    text: ';',
  })
})

test('the first Chinese composition in an empty note has no Latin prefix', async ({ page, context }) => {
  await mockNoteEditorApi(page, '')
  await page.goto('/notes/1/edit')

  const editor = page.locator('.toastui-editor-ww-container .ProseMirror')
  await editor.click()
  await waitForEditorBindings(editor)

  const client = await context.newCDPSession(page)
  await client.send('Input.imeSetComposition', {
    text: 'ni',
    selectionStart: 2,
    selectionEnd: 2,
  })
  await client.send('Input.insertText', { text: '\u4f60' })

  await expect(editor).toHaveText('\u4f60')
})
