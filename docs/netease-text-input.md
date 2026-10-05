# Developer APK keyboard text input

The developer APK uses GameActivity for lifecycle and key events, but retains the
older MainActivity EditText protocol for text. Treating GameActivity registration
as proof that its InputConnection supplies text leaves chat unable to accept typing:
`/` opens `netease_chat_screen` through the key-event path, while subsequent character
callbacks arrive with no active text editor and no GameActivity text state.

The adapter follows the APK's existing Java/JNI contract:

| Interface | Developer APK | Upstream international path |
|---|---|---|
| showKeyboard | `(String, int, boolean, boolean, boolean, int)`; last parameter is IME action | Existing five-argument overload remains supported |
| nativeSetTextboxText | `(String)` | `(String, int, int)` |
| Printable-key lookup | Needed to activate an always-listening edit box | Existing keyboard-autofocus setting controls this workaround |

NetEase enables the existing character-based autofocus behavior and its matching
text guard together: a character received before editor activation is not a complete
textbox value, so forwarding it through nativeSetTextboxText would replace `/` or
other existing content. Once enabled, the shared TextInputHandler accumulates text
and handles editing. Developer text and caret updates go through MainActivity rather
than the unused GameActivity text state. Hardware-keyboard reporting stays unchanged.

No APK, binary address table, Python monkey patch, replacement chat screen, or custom
keyboard UI is needed. The JNI symbols and overloads are the stable entry points.
CocosUIKeyboard lookup warnings were investigated separately; adding its registration
alone did not repair chat and is not part of this patch. Additional GLFW/Carbon keymap
changes were also removed after the smaller adapter passed verification.

## Verification

Use an offline disposable developer world and the actual desktop keyboard path.
Game-internal keyboard simulation bypasses part of this adapter and cannot substitute
for this test:

1. Press `/`, let the chat interface appear, then type `help`. Confirm `/help`, including
   the first character and prefix. Return should execute the local help command.
2. Open normal chat with `T`, type ordinary text, edit with Backspace, and verify the
   complete text. Test Unicode paste separately; it does not prove IME composition.
3. Close the editor and chat, then reopen and repeat to check input-state cleanup.
4. Save/stop the owned test session. Existing instances pin their runtime, so installing
   a newer runtime does not change an already pinned instance.

The final adapter was verified with developer APK 3.9.100.297020 and
3.10.100.299889 on Apple Silicon macOS, including `/help` execution, ordinary
chat text, Unicode paste, and Backspace. IME composition was not independently
verified. Local diagnostic logs
must not record typed content. Keep APKs, screenshots, and experiment traces outside
Git. Similar symptoms on an official iPad client are not evidence of the same cause:
that client uses UIKit/iOS integration and needs its own keyboard/focus trace.
