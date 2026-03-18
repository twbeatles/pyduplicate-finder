from __future__ import annotations

from .common import defaultdict, hashlib, os


class ScanFolderDuplicatesMixin:
    def _trim_file_meta_for_results(self, results):
        if not self._file_meta:
            return
        needed = set()
        for paths in (results or {}).values():
            for p in paths or []:
                if p:
                    needed.add(p)
        if not needed:
            self._file_meta = {}
            return
        self._file_meta = {p: self._file_meta[p] for p in needed if p in self._file_meta}

    def _detect_duplicate_folders(self):
        if not self._file_meta:
            return {}

        root_norms = [self._normalize_path(r) for r in (self.folders or []) if r]
        dir_members = defaultdict(list)

        for abs_path, (size, mtime) in self._file_meta.items():
            if self._stop_event.is_set():
                return {}
            try:
                file_norm = self._normalize_path(abs_path)
                parent = os.path.dirname(abs_path)
                visited = set()
                while parent and parent not in visited:
                    visited.add(parent)
                    parent_norm = self._normalize_path(parent)
                    if not any(file_norm.startswith(r + os.sep) or file_norm == r for r in root_norms):
                        break
                    try:
                        rel = os.path.relpath(abs_path, parent)
                    except Exception:
                        break
                    dir_members[parent].append((rel.replace("\\", "/"), int(size), float(mtime), abs_path))
                    if any(parent_norm == r for r in root_norms):
                        break
                    next_parent = os.path.dirname(parent)
                    if next_parent == parent:
                        break
                    parent = next_parent
            except Exception:
                continue

        quick_groups = defaultdict(list)
        quick_rows = []
        for dir_path, members in dir_members.items():
            if len(members) < 2:
                continue
            file_count = len(members)
            bytes_total = sum(m[1] for m in members)
            quick_input = "\n".join(f"{rel}\0{size}" for rel, size, _m, _p in sorted(members))
            sig_quick = hashlib.blake2b(quick_input.encode("utf-8"), digest_size=20).hexdigest()
            quick_groups[sig_quick].append((dir_path, members, bytes_total, file_count))
            quick_rows.append((dir_path, sig_quick, None, bytes_total, file_count))

        full_hash_by_path = {}
        full_candidate_map = {}
        for sig_quick, dirs in quick_groups.items():
            if len(dirs) < 2:
                continue
            for _dir_path, members, _bytes_total, _file_count in dirs:
                for _rel, size, mtime, abs_path in members:
                    if abs_path not in full_candidate_map:
                        full_candidate_map[abs_path] = (int(size), float(mtime))

        if full_candidate_map:
            full_candidates = [(p, s, m) for p, (s, m) in full_candidate_map.items()]
            full_hash_groups = self._calculate_hashes_parallel(
                full_candidates,
                is_quick_scan=False,
                seed_session_id=self.base_session_id if self.incremental_rescan else None,
            )
            for (_size, digest, _type_str), paths in full_hash_groups.items():
                for p in paths:
                    full_hash_by_path[p] = digest

        final_groups = {}
        full_rows = []
        for sig_quick, dirs in quick_groups.items():
            if len(dirs) < 2:
                continue
            by_full = defaultdict(list)
            for dir_path, members, bytes_total, file_count in dirs:
                parts = []
                for rel, size, mtime, abs_path in sorted(members):
                    if self._stop_event.is_set():
                        return {}
                    full_hash = full_hash_by_path.get(abs_path)
                    if not full_hash:
                        full_hash = f"size:{size}"
                    parts.append(f"{rel}\0{full_hash}")
                sig_full = hashlib.blake2b("\n".join(parts).encode("utf-8"), digest_size=20).hexdigest()
                by_full[sig_full].append((dir_path, bytes_total, file_count))
                full_rows.append((dir_path, sig_quick, sig_full, bytes_total, file_count))

            for sig_full, rows in by_full.items():
                if len(rows) < 2:
                    continue
                paths = sorted(r[0] for r in rows)
                bytes_total = int(rows[0][1])
                file_count = int(rows[0][2])
                final_groups[("FOLDER_DUP", sig_full, bytes_total, file_count)] = paths

        if self.session_id and (quick_rows or full_rows):
            try:
                by_dir = {}
                for d, sq, sf, bt, fc in quick_rows + full_rows:
                    prev = by_dir.get(d)
                    if prev is None:
                        by_dir[d] = (d, sq, sf, bt, fc)
                    else:
                        by_dir[d] = (d, sq or prev[1], sf or prev[2], bt, fc)
                self.cache_manager.save_scan_folder_sigs_batch(self.session_id, list(by_dir.values()))
            except Exception:
                pass

        return final_groups

    def _process_final_group(self, file_hash, size, paths, final_duplicates):
        if not self.byte_compare:
            if self.check_name:
                name_map = defaultdict(list)
                for p in paths:
                    name_key = (file_hash, size, os.path.basename(p))
                    name_map[name_key].append(p)
                for nk, nv in name_map.items():
                    if len(nv) > 1:
                        final_duplicates[nk] = nv
            else:
                final_duplicates[(file_hash, size)] = paths
        else:
            self._byte_compare_group(file_hash, size, paths, final_duplicates)

    def _byte_compare_group(self, file_hash, size, paths, final_duplicates):
        pending = paths[:]
        byte_groups = []

        while pending:
            if self._stop_event.is_set():
                break
            basis = pending.pop(0)
            current_byte_group = [basis]
            non_matches = []

            for candidate in pending:
                if self.compare_files_byte_by_byte(basis, candidate):
                    current_byte_group.append(candidate)
                else:
                    non_matches.append(candidate)

            if len(current_byte_group) > 1:
                byte_groups.append(current_byte_group)

            pending = non_matches

        for idx, grp in enumerate(byte_groups):
            if self.check_name:
                name_map = defaultdict(list)
                for p in grp:
                    name_key = (file_hash, size, os.path.basename(p), f"byte_{idx}")
                    name_map[name_key].append(p)
                for nk, nv in name_map.items():
                    if len(nv) > 1:
                        final_duplicates[nk] = nv
            else:
                final_duplicates[(file_hash, size, f"byte_{idx}")] = grp
