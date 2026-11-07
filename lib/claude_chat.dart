import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';
import 'adaptive.dart';
import 'applications.dart' show shortDate;
import 'paste.dart';
import 'tailor.dart';

const _ink = Color(0xFF172C2A);
const _accent = Color(0xFF146B57);
const _muted = Color(0xFF63716D);
const _blocked = Color(0xFFB3261E);
const _codeBackground = Color(0xFFECEEE8);

// Short enough that each chip fits on one line of a phone screen.
const suggestions = [
  'Check Gmail for application replies',
  'What changed in my projects today?',
  'Draft a follow-up for an application',
];

// The service's limits on photos sent with one message.
const maxPhotos = 5;
const maxPhotoBytes = 3750000;

typedef Photo = ({Uint8List bytes, String name});
typedef PhotoPicker = Future<List<Photo>> Function({
  required bool camera,
  required int limit,
});
// Starts listening for pasted images and returns a function that stops it.
typedef PasteListener = void Function() Function(
  void Function(Future<List<Photo>> photos) onPaste, {
  required int maxBytes,
});

// Picks photos from the phone, shrunk so uploads stay small and within Claude's limits.
Future<List<Photo>> pickPhotos({
  required bool camera,
  required int limit,
}) async {
  final picker = ImagePicker();
  final files = camera
      ? [
          ?await picker.pickImage(
            source: ImageSource.camera,
            maxWidth: 2048,
            maxHeight: 2048,
            imageQuality: 85,
          ),
        ]
      : await picker.pickMultiImage(
          maxWidth: 2048,
          maxHeight: 2048,
          imageQuality: 85,
          limit: limit,
        );
  return [for (final f in files) (bytes: await f.readAsBytes(), name: f.name)];
}

// When a chat was last active, in words.
String chatAge(String iso, DateTime now) {
  final at = DateTime.tryParse(iso)?.toLocal();
  if (at == null) {
    return '';
  }
  final minutes = now.difference(at).inMinutes;
  if (minutes < 1) {
    return 'just now';
  }
  if (minutes < 60) {
    return '$minutes min ago';
  }
  if (minutes < 24 * 60) {
    return '${minutes ~/ 60} h ago';
  }
  return at.toString().split(' ').first;
}

// The service reports a usage warning only when Claude is near or at a limit.
String limitNote(Map limit, {DateTime? now}) {
  final kind = switch (limit['kind']) {
    'five_hour' => '5-hour',
    'seven_day' => 'weekly',
    'seven_day_opus' => 'weekly Opus',
    _ => 'usage',
  };
  final used = limit['used'] is num
      ? '${((limit['used'] as num) * 100).round()}%'
      : 'most';
  final resets = limit['resets_at'] is num
      ? DateTime.fromMillisecondsSinceEpoch(
          (limit['resets_at'] as num).toInt() * 1000,
        ).toLocal()
      : null;
  final today = now ?? DateTime.now();
  final time = resets == null
      ? ''
      : '${resets.hour.toString().padLeft(2, '0')}:${resets.minute.toString().padLeft(2, '0')}';
  // Weekly limits reset days away, so the day matters as much as the time.
  final when = resets == null
      ? ''
      : DateUtils.isSameDay(resets, today)
      ? ' It resets at $time.'
      : ' It resets on ${shortDate(resets)} at $time.';
  return limit['status'] == 'rejected'
      ? 'You have reached your $kind limit.$when'
      : 'You have used $used of your $kind limit.$when';
}

// Splits a reply into prose and ``` code blocks, which render in monospace.
List<({String text, bool code})> replyParts(String text) {
  final parts = <({String text, bool code})>[];
  final chunks = text.split('```');
  for (var i = 0; i < chunks.length; i++) {
    var chunk = chunks[i];
    final code = i.isOdd;
    if (code) {
      // Drop the language name after the opening fence.
      final newline = chunk.indexOf('\n');
      chunk = newline >= 0 && !chunk.substring(0, newline).contains(' ')
          ? chunk.substring(newline + 1)
          : chunk;
      chunk = chunk.replaceFirst(RegExp(r'\n$'), '');
    } else {
      chunk = chunk.trim();
    }
    if (chunk.isNotEmpty) {
      parts.add((text: chunk, code: code));
    }
  }
  return parts;
}

// Talks to Claude Code on the computer that runs the job service.
class ClaudePage extends StatefulWidget {
  final JobsApi Function() api;
  final PhotoPicker pick;
  final PasteListener pastes;
  // The chat to open, such as one tailoring the CV; otherwise the latest.
  final String? chatId;
  const ClaudePage({
    super.key,
    required this.api,
    this.pick = pickPhotos,
    this.pastes = listenForPastedImages,
    this.chatId,
  });
  @override
  State<ClaudePage> createState() => _ClaudePageState();
}

class _ClaudePageState extends State<ClaudePage> {
  late final JobsApi api = widget.api();
  final input = TextEditingController();
  List<Map<String, dynamic>> folders = [], chats = [];
  Map<String, dynamic>? chat;
  List<Map<String, dynamic>> turns = [];
  // Photos waiting to go with the next message.
  List<Photo> attached = [];
  // Photos already sent, by chat and file name, fetched once.
  final Map<String, Future<Uint8List>> images = {};
  String? cwd, error, pollError, model;
  bool loading = true, sending = false;
  Timer? poller;
  late final void Function() stopPastes;
  // Bumped when another chat opens, so late answers for the old one are dropped.
  int generation = 0;

  bool get running => turns.isNotEmpty && turns.last['status'] == 'running';

  @override
  void initState() {
    super.initState();
    stopPastes = widget.pastes(pasted, maxBytes: maxPhotoBytes);
    unawaited(load());
  }

  @override
  void dispose() {
    generation++;
    poller?.cancel();
    stopPastes();
    input.dispose();
    api.close();
    super.dispose();
  }

  String message(Object e) => e.toString().replaceFirst('Exception: ', '');

  Future<void> load() async {
    try {
      final results = await Future.wait([
        api.request('/claude/folders'),
        api.request('/claude/chats'),
      ]);
      final prefs = await SharedPreferences.getInstance();
      if (!mounted) {
        return;
      }
      folders = [
        for (final f in results[0]['folders'] as List)
          Map<String, dynamic>.from(f as Map),
      ];
      final remembered = prefs.getString('claude_cwd');
      setState(() {
        model = [
          results[0]['model'],
          if (results[0]['effort'] != null) '${results[0]['effort']} effort',
        ].whereType<String>().join(' · ');
        cwd = folders.any((f) => f['path'] == remembered)
            ? remembered
            : (results[0]['default'] as String?);
        chats = [
          for (final c in results[1]['chats'] as List)
            Map<String, dynamic>.from(c as Map),
        ];
        loading = false;
      });
      // Pick up where the last conversation left off.
      if (widget.chatId != null) {
        await open(widget.chatId!);
      } else if (chats.isNotEmpty) {
        await open(chats.first['id'] as String);
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          error = message(e);
          loading = false;
        });
      }
    }
  }

  Future<void> refreshChats() async {
    try {
      final result = await api.request('/claude/chats');
      if (mounted) {
        setState(() {
          chats = [
            for (final c in result['chats'] as List)
              Map<String, dynamic>.from(c as Map),
          ];
        });
      }
    } catch (_) {
      // The list in hand is still useful.
    }
  }

  Future<void> open(String id) async {
    final mine = ++generation;
    poller?.cancel();
    try {
      final result = await api.request('/claude/chats/$id?from=0');
      if (!mounted || mine != generation) {
        return;
      }
      setState(() {
        error = pollError = null;
        merge(Map<String, dynamic>.from(result['chat'] as Map));
      });
      schedulePoll();
    } catch (e) {
      if (mounted && mine == generation) {
        setState(() {
          error = message(e);
        });
      }
    }
  }

  // Applies a reply from the service, which holds every turn from its start index on.
  void merge(Map<String, dynamic> update) {
    final start = (update['start'] as num?)?.toInt() ?? 0;
    final fresh = [
      for (final t in update['turns'] as List)
        Map<String, dynamic>.from(t as Map),
    ];
    if (chat?['id'] != update['id']) {
      turns = [];
    }
    turns = [...turns.take(start), ...fresh];
    chat = update..remove('turns');
  }

  void schedulePoll() {
    poller?.cancel();
    if (!running) {
      return;
    }
    final mine = generation;
    poller = Timer(const Duration(seconds: 1), () => unawaited(poll(mine)));
  }

  Future<void> poll(int mine) async {
    final id = chat?['id'];
    if (id == null || mine != generation) {
      return;
    }
    try {
      final result = await api.request(
        '/claude/chats/$id?from=${turns.length - 1}',
      );
      if (!mounted || mine != generation) {
        return;
      }
      setState(() {
        pollError = null;
        merge(Map<String, dynamic>.from(result['chat'] as Map));
      });
      if (!running) {
        unawaited(refreshChats());
      }
    } catch (e) {
      if (!mounted || mine != generation) {
        return;
      }
      setState(() {
        pollError = '${message(e)} Retrying…';
      });
    }
    schedulePoll();
  }

  Future<void> attach() async {
    final camera = await showModalBottomSheet<bool>(
      context: context,
      showDragHandle: true,
      builder: (sheet) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.photo_library_outlined),
              title: const Text('Choose photos'),
              onTap: () => Navigator.pop(sheet, false),
            ),
            ListTile(
              leading: const Icon(Icons.photo_camera_outlined),
              title: const Text('Take a photo'),
              onTap: () => Navigator.pop(sheet, true),
            ),
          ],
        ),
      ),
    );
    if (camera == null) {
      return;
    }
    try {
      final picked = await widget.pick(
        camera: camera,
        limit: maxPhotos - attached.length,
      );
      if (mounted) {
        add(picked);
      }
    } on PlatformException catch (e) {
      if (mounted) {
        setState(() {
          error = e.message ?? 'The photos could not be opened.';
        });
      }
    }
  }

  // Images pasted into the page, such as a screenshot, on the web.
  Future<void> pasted(Future<List<Photo>> photos) async {
    // A send in flight clears the photos when it finishes, so a paste would be lost.
    if (sending || (chat == null && cwd == null)) {
      return;
    }
    try {
      final pasted = await photos;
      if (mounted) {
        add(pasted);
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          error = 'The pasted image could not be read.';
        });
      }
    }
  }

  // Adds photos to the next message, within the service's limits.
  void add(List<Photo> photos) {
    final fits = photos.where((p) => p.bytes.length <= maxPhotoBytes).toList();
    final room = maxPhotos - attached.length;
    setState(() {
      error = fits.length < photos.length
          ? 'Photos over ${maxPhotoBytes ~/ 1000000} MB were left out.'
          : fits.length > room
          ? 'A message takes up to $maxPhotos photos.'
          : null;
      attached = [...attached, ...fits.take(room)];
    });
  }

  // A sent photo, fetched from the service the first time it shows.
  Future<Uint8List> image(String chatId, String name) =>
      images['$chatId/$name'] ??= api
          .file('/claude/chats/$chatId/images/$name')
          .then((f) => f.bytes)
          .catchError((Object e) {
            // Try again on the next build.
            images.remove('$chatId/$name');
            throw e;
          });

  Future<void> send([String? text]) async {
    final prompt = (text ?? input.text).trim();
    final photos = attached;
    if ((prompt.isEmpty && photos.isEmpty) || sending || running) {
      return;
    }
    setState(() {
      sending = true;
      error = null;
    });
    final mine = ++generation;
    try {
      final id = chat?['id'];
      final body = {
        'text': prompt,
        if (photos.isNotEmpty)
          'images': [for (final p in photos) base64Encode(p.bytes)],
      };
      final timeout = Duration(seconds: photos.isEmpty ? 20 : 120);
      final result = id == null
          ? await api.request(
              '/claude/chats',
              body: {'cwd': cwd, ...body},
              timeout: timeout,
            )
          : await api.request(
              '/claude/chats/$id/messages',
              body: body,
              timeout: timeout,
            );
      if (!mounted || mine != generation) {
        return;
      }
      input.clear();
      final update = Map<String, dynamic>.from(result['chat'] as Map);
      // The photos just sent are already on the phone.
      final sent = (update['turns'] as List).last['images'] as List? ?? [];
      for (var i = 0; i < sent.length && i < photos.length; i++) {
        images['${update['id']}/${sent[i]['name']}'] = Future.value(
          photos[i].bytes,
        );
      }
      setState(() {
        attached = [];
        merge(update);
      });
      schedulePoll();
      if (id == null) {
        unawaited(refreshChats());
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          error = message(e);
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          sending = false;
        });
      }
    }
  }

  Future<void> stop() async {
    final id = chat?['id'];
    if (id == null) {
      return;
    }
    try {
      await api.request('/claude/chats/$id/stop', body: {});
    } catch (e) {
      if (mounted) {
        setState(() {
          error = message(e);
        });
      }
    }
  }

  void startNew() {
    generation++;
    poller?.cancel();
    setState(() {
      chat = null;
      turns = [];
      error = pollError = null;
    });
  }

  Future<void> remove(Map<String, dynamic> c) async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (dialog) => AlertDialog(
        title: const Text('Delete this chat?'),
        content: Text(
          '“${c['title']}” disappears from the app. Claude Code keeps its own session files on the computer.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialog, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialog, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (sure != true) {
      return;
    }
    try {
      await api.request('/claude/chats/${c['id']}', method: 'DELETE');
      if (chat?['id'] == c['id']) {
        startNew();
      }
      await refreshChats();
    } catch (e) {
      if (mounted) {
        setState(() {
          error = message(e);
        });
      }
    }
  }

  Future<void> showChats() async {
    await refreshChats();
    if (!mounted) {
      return;
    }
    final now = DateTime.now();
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (sheet) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: .6,
        maxChildSize: .9,
        builder: (sheet, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(12, 0, 12, 24),
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(12, 0, 12, 8),
              child: Text(
                'Chats',
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800),
              ),
            ),
            if (chats.isEmpty)
              const Padding(
                padding: EdgeInsets.all(12),
                child: Text('No chats yet.'),
              ),
            for (final c in chats)
              ListTile(
                selected: c['id'] == chat?['id'],
                title: Text(
                  c['title'].toString(),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                subtitle: Text(
                  '${c['folder']} · ${c['running'] == true ? 'working' : chatAge(c['updated_at'].toString(), now)}',
                ),
                onTap: () {
                  Navigator.pop(sheet);
                  unawaited(open(c['id'] as String));
                },
                trailing: IconButton(
                  tooltip: 'Delete chat',
                  icon: const Icon(Icons.delete_outline),
                  onPressed: () {
                    Navigator.pop(sheet);
                    unawaited(remove(c));
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }

  void chooseFolder() {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (sheet) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: .7,
        maxChildSize: .9,
        builder: (sheet, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(12, 0, 12, 24),
          children: [
            for (final f in folders)
              ListTile(
                leading: Icon(
                  f['path'] == cwd ? Icons.folder : Icons.folder_outlined,
                  color: f['path'] == cwd ? _accent : null,
                ),
                title: Text(f['name'].toString()),
                subtitle: Text(
                  f['path'].toString(),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                onTap: () async {
                  Navigator.pop(sheet);
                  setState(() {
                    cwd = f['path'] as String;
                  });
                  final prefs = await SharedPreferences.getInstance();
                  await prefs.setString('claude_cwd', cwd!);
                },
              ),
          ],
        ),
      ),
    );
  }

  String folderName(String? path) {
    for (final f in folders) {
      if (f['path'] == path) {
        return f['name'].toString();
      }
    }
    return path?.split('/').last ?? 'No folder';
  }

  Widget emptyState() => ListView(
    padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
    children: [
      const Text(
        'Talk to Claude.',
        style: TextStyle(
          fontSize: 32,
          fontWeight: FontWeight.w800,
          letterSpacing: -1.3,
          color: _ink,
        ),
      ),
      const SizedBox(height: 8),
      Text(
        'Claude Code on the computer that runs your service, with your settings, files and connectors. Add photos with the photo button${kIsWeb ? ', or paste a screenshot into the message box' : ''}. Auto mode blocks risky actions, and anything that needs approval is refused.',
        style: const TextStyle(color: _muted, fontSize: 15),
      ),
      if (model?.isNotEmpty == true) ...[
        const SizedBox(height: 8),
        Text(model!, style: const TextStyle(color: _accent, fontSize: 13)),
      ],
      const SizedBox(height: 20),
      Card(
        child: ListTile(
          leading: const Icon(Icons.folder_outlined, color: _accent),
          title: Text(folderName(cwd)),
          subtitle: const Text('Claude works in this folder'),
          trailing: const Icon(Icons.chevron_right),
          onTap: folders.isEmpty ? null : chooseFolder,
        ),
      ),
      const SizedBox(height: 20),
      Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          for (final s in suggestions)
            ActionChip(
              label: Text(s),
              onPressed: cwd == null || sending ? null : () => send(s),
            ),
        ],
      ),
    ],
  );

  List<Widget> turnWidgets(Map<String, dynamic> turn) {
    final items = (turn['items'] as List? ?? const [])
        .map((i) => Map<String, dynamic>.from(i as Map))
        .toList();
    final status = turn['status'];
    final chatId = chat?['id'].toString() ?? '';
    return [
      _UserBubble(
        text: turn['prompt'].toString(),
        images: [
          for (final i in turn['images'] as List? ?? const [])
            image(chatId, (i as Map)['name'].toString()),
        ],
      ),
      for (final item in items)
        switch (item['kind']) {
          'text' => _ReplyBubble(text: item['text'].toString()),
          'blocked' => _ToolRow(item: item, blocked: true),
          _ => _ToolRow(item: item),
        },
      if (status == 'running')
        const _Note(text: 'Claude is working…', working: true),
      if (status == 'stopped') const _Note(text: 'Stopped.'),
      if (status == 'interrupted')
        const _Note(
          text: 'Interrupted: the service restarted while Claude worked.',
        ),
      if (status == 'error')
        _Note(
          text: (turn['error'] ?? 'Claude Code failed.').toString(),
          error: true,
        ),
      if (turn['limit'] is Map) _Note(text: limitNote(turn['limit'] as Map)),
    ];
  }

  void notify(String text, {SnackBarAction? action}) {
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(SnackBar(content: Text(text), action: action));
  }

  // The bar above a tailoring chat, with the CV's files once Claude builds them.
  Widget tailorBar(Map<String, dynamic> tailor) {
    final id = (tailor['id'] ?? '').toString();
    final company = (tailor['company'] ?? '').toString();
    return TailorBar(
      tailor: tailor,
      download: id.isEmpty
          ? null
          : () => unawaited(downloadTailored(api, id, company, notify)),
      report: id.isEmpty
          ? null
          : () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => ReportPage(
                  api: widget.api,
                  id: id,
                  title: '$company — ${tailor['title']}',
                ),
              ),
            ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final current = chat;
    final children = [for (final t in turns) ...turnWidgets(t)];
    final tailor = current?['tailor'] is Map
        ? Map<String, dynamic>.from(current!['tailor'] as Map)
        : null;
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              current == null ? 'Claude' : current['title'].toString(),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
            if (current != null)
              Text(
                current['folder'].toString(),
                style: const TextStyle(fontSize: 12, color: _muted),
              ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Chats',
            onPressed: loading ? null : showChats,
            icon: const Icon(Icons.history),
          ),
          IconButton(
            tooltip: 'New chat',
            onPressed: loading || current == null ? null : startNew,
            icon: const Icon(Icons.add_comment_outlined),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: ContentWidth(
        child: loading
            ? const Center(child: CircularProgressIndicator())
            : Column(
                children: [
                  if (tailor != null) tailorBar(tailor),
                  Expanded(
                    child: current == null
                        ? emptyState()
                        // Reversed, so the newest message sits above the input and stays in view.
                        : ListView(
                            reverse: true,
                            padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                            children: children.reversed.toList(),
                          ),
                  ),
                  if (error != null || pollError != null)
                    Padding(
                      padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
                      child: Text(
                        (error ?? pollError)!,
                        style: const TextStyle(color: _blocked),
                      ),
                    ),
                  if (attached.isNotEmpty)
                    SizedBox(
                      height: 76,
                      child: ListView(
                        scrollDirection: Axis.horizontal,
                        padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                        children: [
                          for (final (i, p) in attached.indexed)
                            _Attached(
                              photo: p,
                              onRemove: () => setState(() {
                                attached = [...attached]..removeAt(i);
                              }),
                            ),
                        ],
                      ),
                    ),
                  SafeArea(
                    top: false,
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(4, 4, 12, 12),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          IconButton(
                            tooltip: 'Add photos',
                            onPressed:
                                sending ||
                                    running ||
                                    attached.length >= maxPhotos ||
                                    (current == null && cwd == null)
                                ? null
                                : attach,
                            icon: const Icon(
                              Icons.add_photo_alternate_outlined,
                            ),
                          ),
                          Expanded(
                            child: TextField(
                              controller: input,
                              minLines: 1,
                              maxLines: 6,
                              maxLength: 20000,
                              buildCounter: (
                                context, {
                                required currentLength,
                                required isFocused,
                                maxLength,
                              }) => null,
                              textCapitalization: TextCapitalization.sentences,
                              decoration: InputDecoration(
                                hintText: current == null
                                    ? 'Ask Claude in ${folderName(cwd)}'
                                    : 'Message Claude',
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          running
                              ? IconButton.filledTonal(
                                  tooltip: 'Stop Claude',
                                  onPressed: stop,
                                  icon: const Icon(Icons.stop_rounded),
                                )
                              : IconButton.filled(
                                  tooltip: 'Send',
                                  onPressed:
                                      sending ||
                                          (current == null && cwd == null)
                                      ? null
                                      : send,
                                  icon: sending
                                      ? const SizedBox(
                                          width: 18,
                                          height: 18,
                                          child: CircularProgressIndicator(
                                            strokeWidth: 2,
                                            color: Colors.white,
                                          ),
                                        )
                                      : const Icon(Icons.arrow_upward_rounded),
                                ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}

class _UserBubble extends StatelessWidget {
  final String text;
  final List<Future<Uint8List>> images;
  const _UserBubble({required this.text, this.images = const []});
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 16, bottom: 8, left: 48),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        if (images.isNotEmpty)
          Wrap(
            alignment: WrapAlignment.end,
            spacing: 6,
            runSpacing: 6,
            children: [for (final i in images) _SentPhoto(bytes: i)],
          ),
        if (images.isNotEmpty && text.isNotEmpty) const SizedBox(height: 6),
        if (text.isNotEmpty)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: _accent,
              borderRadius: BorderRadius.circular(18),
            ),
            child: SelectableText(
              text,
              style: const TextStyle(color: Colors.white),
            ),
          ),
      ],
    ),
  );
}

// A photo waiting to be sent, with a button to take it out.
class _Attached extends StatelessWidget {
  final Photo photo;
  final VoidCallback onRemove;
  const _Attached({required this.photo, required this.onRemove});
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(right: 8),
    child: Stack(
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(10),
          child: Image.memory(
            photo.bytes,
            width: 64,
            height: 64,
            fit: BoxFit.cover,
            semanticLabel: photo.name,
          ),
        ),
        Positioned(
          top: 0,
          right: 0,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: onRemove,
            child: Container(
              margin: const EdgeInsets.all(3),
              decoration: const BoxDecoration(
                color: Colors.black54,
                shape: BoxShape.circle,
              ),
              padding: const EdgeInsets.all(2),
              child: Icon(
                Icons.close,
                size: 16,
                color: Colors.white,
                semanticLabel: 'Remove ${photo.name}',
              ),
            ),
          ),
        ),
      ],
    ),
  );
}

// A sent photo; tap to see it full screen.
class _SentPhoto extends StatelessWidget {
  final Future<Uint8List> bytes;
  const _SentPhoto({required this.bytes});
  @override
  Widget build(BuildContext context) => FutureBuilder<Uint8List>(
    future: bytes,
    builder: (context, snapshot) {
      final data = snapshot.data;
      return GestureDetector(
        onTap: data == null
            ? null
            : () => showDialog<void>(
                context: context,
                builder: (dialog) => Dialog.fullscreen(
                  backgroundColor: Colors.black,
                  child: Stack(
                    children: [
                      Center(
                        child: InteractiveViewer(child: Image.memory(data)),
                      ),
                      SafeArea(
                        child: IconButton(
                          tooltip: 'Close',
                          color: Colors.white,
                          onPressed: () => Navigator.pop(dialog),
                          icon: const Icon(Icons.close),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(14),
          child: Container(
            width: 120,
            height: 120,
            color: _codeBackground,
            child: data != null
                ? Image.memory(data, fit: BoxFit.cover)
                : Icon(
                    snapshot.hasError
                        ? Icons.broken_image_outlined
                        : Icons.image_outlined,
                    color: _muted,
                  ),
          ),
        ),
      );
    },
  );
}

class _ReplyBubble extends StatelessWidget {
  final String text;
  const _ReplyBubble({required this.text});
  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.centerLeft,
    child: Container(
      margin: const EdgeInsets.only(bottom: 8, right: 24),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final part in replyParts(text))
            part.code
                ? Container(
                    width: double.infinity,
                    margin: const EdgeInsets.symmetric(vertical: 6),
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: _codeBackground,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      child: SelectableText(
                        part.text,
                        style: const TextStyle(
                          fontFamily: 'monospace',
                          fontSize: 12.5,
                        ),
                      ),
                    ),
                  )
                : Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: SelectableText(
                      part.text,
                      style: const TextStyle(color: _ink, height: 1.35),
                    ),
                  ),
        ],
      ),
    ),
  );
}

class _ToolRow extends StatelessWidget {
  final Map<String, dynamic> item;
  final bool blocked;
  const _ToolRow({required this.item, this.blocked = false});
  @override
  Widget build(BuildContext context) {
    final name = item['name'].toString();
    final icon = blocked
        ? Icons.block
        : switch (name) {
            'Bash' => Icons.terminal,
            'Read' || 'Write' || 'Edit' => Icons.description_outlined,
            'Grep' || 'Glob' || 'WebSearch' => Icons.search,
            'WebFetch' => Icons.public,
            _ => Icons.build_outlined,
          };
    final color = blocked ? _blocked : _muted;
    final detail = item['text'].toString();
    return Padding(
      padding: const EdgeInsets.only(bottom: 6, left: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 15, color: color),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              '${blocked ? 'Blocked by auto mode: ' : ''}$name${detail.isEmpty ? '' : ' · $detail'}',
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 12, color: color),
            ),
          ),
        ],
      ),
    );
  }
}

class _Note extends StatelessWidget {
  final String text;
  final bool working, error;
  const _Note({required this.text, this.working = false, this.error = false});
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 4, bottom: 8, left: 4),
    child: Row(
      children: [
        if (working) ...[
          const SizedBox(
            width: 14,
            height: 14,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
          const SizedBox(width: 10),
        ],
        Expanded(
          child: Text(
            text,
            style: TextStyle(
              fontSize: 13,
              color: error ? _blocked : _muted,
              fontStyle: working ? FontStyle.italic : FontStyle.normal,
            ),
          ),
        ),
      ],
    ),
  );
}
