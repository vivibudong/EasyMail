<template>
  <AppLayout
    title="后台面板"
    description="面向多邮箱账号的统一管理与收件工作台。"
    :metrics="headerMetrics"
    :non-success-accounts="nonSuccessAccounts"
    :queue-details="queueDetails"
    :show-task-button="true"
    @show-account-detail="handleShowAccountDetail"
    @open-task-center="openTaskCenter"
  >
    <div class="h-[calc(100vh-74px)]">
      <section class="card flex h-full flex-col overflow-hidden">
        <div class="card-header flex flex-wrap items-center gap-2 px-4 py-3">
          <button class="btn btn-secondary btn-sm" @click="triggerImport">导入账号</button>
          <button class="btn btn-danger btn-sm" @click="handleReceiveAll">收取全部</button>
          <button class="btn btn-secondary btn-sm" :disabled="!hasSelection" @click="handleReceiveChecked">
            勾选收件
          </button>
          <button class="btn btn-secondary btn-sm" :disabled="!hasSelection" @click="handleReloginChecked">
            重新登录
          </button>
          <button class="btn btn-secondary btn-sm" :disabled="!hasSelection" @click="handleDeleteChecked">
            删除勾选
          </button>
          <button class="btn btn-secondary btn-sm" @click="handleExportAccounts">导出邮箱</button>
          <div class="min-w-[220px] flex-1">
            <div class="flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-dark-400">
              <span>当前分组：{{ selectedGroupLabel }}</span>
              <span>当前邮箱：{{ selectedAccountEmail || '全部邮箱' }}</span>
              <span>失败账号：{{ nonSuccessAccounts.length }}</span>
            </div>
            <div class="progress mt-1.5 h-1.5">
              <div class="progress-bar" :style="{ width: `${dashboard?.overview.queue.percent ?? 0}%` }"></div>
            </div>
          </div>
          <input
            v-model="searchTerm"
            class="input min-w-[180px] max-w-[240px] py-2 text-xs"
            type="text"
            placeholder="全局搜索邮箱 / 主题 / 发件人"
          />
          <RouterLink to="/settings" class="btn btn-secondary btn-sm">设置</RouterLink>
          <input ref="fileInput" class="hidden" type="file" accept=".txt" @change="handleImportFile" />
        </div>

        <div class="card-body flex-1 overflow-hidden p-0">
          <div class="mail-workbench">
            <aside class="mail-pane border-r border-gray-100 dark:border-dark-800">
              <div class="pane-scroll space-y-3 py-2">
                <div>
                  <div class="mb-1 flex items-center justify-between gap-2 px-1">
                    <button
                      class="flex items-center gap-1 text-[12px] font-semibold text-gray-700 dark:text-dark-200"
                      @click="groupSectionOpen = !groupSectionOpen"
                    >
                      <span>{{ groupSectionOpen ? '▾' : '▸' }}</span>
                      <span>分组</span>
                    </button>
                    <button class="btn btn-secondary btn-sm px-2 py-1" @click="handleCreateGroup">+</button>
                  </div>
                  <div v-if="groupSectionOpen" class="space-y-1">
                    <button
                      v-for="group in groupOptions"
                      :key="group.key"
                      class="flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-[12px] transition-all duration-200"
                      :class="
                        selectedGroupKey === group.key
                          ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/10 dark:text-primary-300'
                          : 'text-gray-600 hover:bg-gray-50 dark:text-dark-300 dark:hover:bg-dark-800/60'
                      "
                      @click="selectGroup(group.key)"
                      @contextmenu.prevent="openGroupContextMenu($event, group)"
                    >
                      <span
                        class="inline-block h-2 w-2 flex-shrink-0 rounded-full"
                        :style="{ backgroundColor: group.color || '#D6EAF8' }"
                      ></span>
                      <span class="truncate">{{ group.label }}({{ group.accountCount }})</span>
                    </button>
                  </div>
                </div>

                <div>
                  <div class="mb-1 flex items-center justify-between gap-2 px-1">
                    <button
                      class="flex items-center gap-1 text-[12px] font-semibold text-gray-700 dark:text-dark-200"
                      @click="tagSectionOpen = !tagSectionOpen"
                    >
                      <span>{{ tagSectionOpen ? '▾' : '▸' }}</span>
                      <span>标签</span>
                    </button>
                    <button class="btn btn-secondary btn-sm px-2 py-1" @click="handleCreateTag">+</button>
                  </div>
                  <div v-if="tagSectionOpen" class="space-y-1">
                    <button
                      class="flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-[12px] transition-all duration-200"
                      :class="
                        !selectedTagKey
                          ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/10 dark:text-primary-300'
                          : 'text-gray-600 hover:bg-gray-50 dark:text-dark-300 dark:hover:bg-dark-800/60'
                      "
                      @click="selectTag('')"
                    >
                      <span class="inline-block h-2 w-2 flex-shrink-0 rounded-full bg-gray-300"></span>
                      <span class="truncate">全部标签</span>
                    </button>
                    <button
                      v-for="tag in tagOptions"
                      :key="tag.key"
                      class="flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-[12px] transition-all duration-200"
                      :class="
                        selectedTagKey === tag.key
                          ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/10 dark:text-primary-300'
                          : 'text-gray-600 hover:bg-gray-50 dark:text-dark-300 dark:hover:bg-dark-800/60'
                      "
                      @click="selectTag(tag.key)"
                      @contextmenu.prevent="openTagContextMenu($event, tag)"
                    >
                      <span
                        class="inline-block h-2 w-2 flex-shrink-0 rounded-full"
                        :style="{ backgroundColor: tag.color || '#BFDBFE' }"
                      ></span>
                      <span class="truncate">{{ tag.label }}({{ tag.accountCount }})</span>
                    </button>
                  </div>
                </div>
              </div>
            </aside>

            <aside class="mail-pane border-r border-gray-100 dark:border-dark-800">
              <div class="pane-toolbar">
                <label class="inline-flex items-center gap-2 text-xs text-gray-700 dark:text-dark-300">
                  <input
                    :checked="allChecked"
                    type="checkbox"
                    @change="toggleAllAccounts(($event.target as HTMLInputElement).checked)"
                  />
                  全选
                </label>
                <button class="btn btn-secondary btn-sm px-2 py-1" @click="filterAllMails">全部邮件</button>
              </div>

              <div class="pane-status">
                <div class="truncate">当前：{{ selectedAccountEmail || '全部邮箱' }}</div>
                <div
                  v-if="selectedAccount?.last_error_summary"
                  class="mt-1 flex items-center gap-2 text-red-500"
                >
                  <span class="truncate">{{ selectedAccount.last_error_summary }}</span>
                  <button
                    class="rounded-md border border-red-200 px-1.5 py-0.5 text-[10px] text-red-500 hover:bg-red-50 dark:border-red-800/50 dark:hover:bg-red-900/20"
                    @click="openAccountDetail(selectedAccount)"
                  >
                    详情
                  </button>
                </div>
                <div class="mt-1 truncate text-[11px] text-gray-500 dark:text-dark-400">
                  认证：{{ selectedAccount?.auth_method || '-' }}
                </div>
                <div v-if="!selectedAccount?.last_error_summary" class="mt-1 truncate">
                  状态：{{ selectedAccount?.status || '-' }}
                </div>
              </div>

              <div ref="accountListRef" class="pane-scroll overflow-hidden">
                <button
                  v-for="account in paginatedAccounts"
                  :key="account.email"
                  class="account-row"
                  :class="{ 'account-row-active': selectedAccountEmail === account.email }"
                  @click="filterAccount(account.email)"
                  @contextmenu.prevent="openContextMenu($event, account.email)"
                >
                  <input
                    class="mt-0.5"
                    type="checkbox"
                    :checked="checkedAccounts.includes(account.email)"
                    @click.stop
                    @change="toggleAccount(account.email, ($event.target as HTMLInputElement).checked)"
                  />
                  <span
                    class="mt-1 inline-block h-2 w-2 rounded-full"
                    :style="{ backgroundColor: account.flag_color || '#D6EAF8' }"
                  ></span>
                  <div class="min-w-0 flex-1 text-left">
                    <div class="truncate text-[12px] font-medium" :class="statusTextClass(account.status)">
                      {{ account.index }}. {{ account.email }}
                    </div>
                    <div class="mt-0.5 flex items-center gap-1.5 text-[10px] text-gray-500 dark:text-dark-400">
                      <span>{{ account.group_name }}</span>
                      <span>·</span>
                      <span>{{ account.status }}</span>
                      <span v-if="account.unseen_count > 0" class="badge badge-primary px-2 py-0">
                        {{ account.unseen_count }}
                      </span>
                    </div>
                    <div v-if="visibleAccountTags(account).length" class="mt-1 flex flex-wrap gap-1">
                      <span
                        v-for="tagName in visibleAccountTags(account)"
                        :key="tagName"
                        class="inline-flex items-center gap-1 rounded-full px-1.5 py-0 text-[10px]"
                        :style="tagPillStyle(tagName)"
                      >
                        <span class="inline-block h-1.5 w-1.5 rounded-full" :style="{ backgroundColor: tagColor(tagName) }"></span>
                        {{ tagName }}
                      </span>
                      <span
                        v-if="account.tags.length > visibleAccountTags(account).length"
                        class="text-[10px] text-gray-400 dark:text-dark-500"
                      >
                        +{{ account.tags.length - visibleAccountTags(account).length }}
                      </span>
                    </div>
                  </div>
                  <button
                    class="rounded-md px-1.5 py-0.5 text-[10px] text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-dark-700 dark:hover:text-dark-200"
                    @click.stop="copyEmail(account.email)"
                  >
                    复制
                  </button>
                </button>

                <div
                  v-if="!paginatedAccounts.length"
                  class="empty-state rounded-2xl border border-dashed border-gray-200 py-8 dark:border-dark-700"
                >
                  <div class="empty-state-title text-sm">当前分组没有邮箱</div>
                  <div class="empty-state-description text-xs">创建分组后可在邮箱右键菜单中分配。</div>
                </div>
              </div>

              <div class="border-t border-gray-100 px-3 py-2 dark:border-dark-800">
                <div class="flex items-center justify-between text-[11px] text-gray-500 dark:text-dark-400">
                  <span>邮箱 {{ accountPage }}/{{ totalAccountPages }}</span>
                  <div class="flex items-center gap-1.5">
                    <button class="btn btn-secondary btn-sm px-2 py-1" :disabled="accountPage <= 1" @click="accountPage--">
                      上一页
                    </button>
                    <button
                      class="btn btn-secondary btn-sm px-2 py-1"
                      :disabled="accountPage >= totalAccountPages"
                      @click="accountPage++"
                    >
                      下一页
                    </button>
                  </div>
                </div>
              </div>
            </aside>

            <section class="mail-pane border-r border-gray-100 dark:border-dark-800">
              <div class="pane-toolbar">
                <div>
                  <div class="text-sm font-semibold text-gray-900 dark:text-white">邮件列表</div>
                  <div class="text-[11px] text-gray-500 dark:text-dark-400">
                    {{ visibleMailsAll.length }} 封
                  </div>
                </div>
                <button class="btn btn-secondary btn-sm px-2 py-1" @click="refreshState()">刷新</button>
              </div>

              <div ref="mailListRef" class="pane-scroll overflow-hidden space-y-3">
                <div v-for="group in groupedMails" :key="group.label">
                  <div class="mb-1 px-1 text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                    {{ group.label }}
                  </div>
                  <button
                    v-for="mail in group.items"
                    :key="mail.local_key"
                    class="mail-row"
                    :class="{
                      'mail-row-unread': mail.is_unread,
                      'mail-row-active': selectedMailKey === mail.local_key,
                    }"
                    @click="handleOpenMail(mail)"
                  >
                    <div class="flex items-start gap-2">
                      <button
                        class="mt-[1px] text-sm leading-none transition-colors"
                        :class="mail.is_starred ? 'text-amber-400' : 'text-gray-300 hover:text-amber-300'"
                        @click.stop="handleToggleStar(mail)"
                      >
                        {{ mail.is_starred ? '★' : '☆' }}
                      </button>
                      <div class="min-w-0 flex-1">
                        <div
                          class="truncate text-[12px]"
                          :class="
                            mail.is_unread
                              ? 'font-semibold text-gray-900 dark:text-white'
                              : 'text-gray-600 dark:text-dark-300'
                          "
                        >
                          {{ mail.subject }}
                        </div>
                        <div class="mt-0.5 flex items-center gap-1.5 truncate text-[10px] text-gray-500 dark:text-dark-400">
                          <span class="badge px-2 py-0" :class="folderBadgeClass(mail.folder)">{{ mail.folder }}</span>
                          <span>{{ mail.account_email }}</span>
                          <span>|</span>
                          <span>{{ mail.date_text }}</span>
                        </div>
                      </div>
                      <span
                        v-if="mail.is_unread"
                        class="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-primary-500"
                      ></span>
                    </div>
                  </button>
                </div>

                <div
                  v-if="!groupedMails.length"
                  class="empty-state rounded-2xl border border-dashed border-gray-200 py-8 dark:border-dark-700"
                >
                  <Icon name="inbox" size="lg" class="empty-state-icon" />
                  <div class="empty-state-title text-sm">暂无邮件</div>
                  <div class="empty-state-description text-xs">请先登录并收件，或切换到其他筛选。</div>
                </div>
              </div>

              <div class="border-t border-gray-100 px-3 py-2 dark:border-dark-800">
                <div class="flex items-center justify-between text-[11px] text-gray-500 dark:text-dark-400">
                  <span>邮件 {{ mailPage }}/{{ totalMailPages }}</span>
                  <div class="flex items-center gap-1.5">
                    <button class="btn btn-secondary btn-sm px-2 py-1" :disabled="mailPage <= 1" @click="mailPage--">
                      上一页
                    </button>
                    <button class="btn btn-secondary btn-sm px-2 py-1" :disabled="mailPage >= totalMailPages" @click="mailPage++">
                      下一页
                    </button>
                  </div>
                </div>
              </div>
            </section>

            <section class="mail-pane">
              <div class="pane-toolbar">
                <div class="min-w-0">
                  <div class="truncate text-sm font-semibold text-gray-900 dark:text-white">
                    {{ selectedMailDetail?.subject || '正文预览' }}
                  </div>
                  <div class="truncate text-[11px] text-gray-500 dark:text-dark-400">
                    {{
                      selectedMailDetail
                        ? `${selectedMailDetail.folder} | ${selectedMailDetail.account_email} | ${selectedMailDetail.date_text}`
                        : '等待选择邮件'
                    }}
                  </div>
                </div>
                <div class="flex items-center gap-2">
                  <button
                    v-if="selectedMailDetail"
                    class="text-lg leading-none"
                    :class="selectedMailDetail.is_starred ? 'text-amber-400' : 'text-gray-300 hover:text-amber-300'"
                    @click="handleToggleStar(selectedMailDetail)"
                  >
                    {{ selectedMailDetail.is_starred ? '★' : '☆' }}
                  </button>
                  <button
                    v-if="selectedMailKey"
                    class="btn btn-secondary btn-sm px-2 py-1"
                    @click="refreshMailBody"
                  >
                    刷新正文
                  </button>
                </div>
              </div>

              <div class="px-4 pb-2">
                <div class="mb-1.5 text-[11px] text-gray-500 dark:text-dark-400">
                  {{ bodyStatusText }}
                </div>
                <div class="progress h-1.5">
                  <div class="progress-bar" :style="{ width: `${bodyProgress}%` }"></div>
                </div>
              </div>

              <div class="pane-scroll">
                <div
                  v-if="!selectedMailDetail"
                  class="empty-state rounded-2xl border border-dashed border-gray-200 py-10 dark:border-dark-700"
                >
                  <Icon name="mail" size="lg" class="empty-state-icon" />
                  <div class="empty-state-title text-sm">请选择一封邮件</div>
                  <div class="empty-state-description text-xs">正文将被后台下载并写入本地缓存。</div>
                </div>
                <pre v-else class="mail-body">{{ selectedMailDetail.body_text || '(正文为空)' }}</pre>
              </div>
            </section>
          </div>
        </div>
      </section>

      <div
        v-if="contextMenu.visible"
        class="dropdown fixed z-[70] w-56 p-0"
        :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }"
      >
        <template v-if="contextMenu.kind === 'account'">
          <div class="px-3 py-2 text-xs font-semibold text-gray-500 dark:text-dark-400">账号操作</div>
          <button class="dropdown-item w-full" @click="openEditAccountFromMenu">编辑账号</button>
          <button class="dropdown-item w-full" @click="runSingleReceive(contextMenu.email)">收件</button>
          <button class="dropdown-item w-full" @click="runSingleRelogin(contextMenu.email)">重新登录</button>
          <button class="dropdown-item w-full" @click="openGraphReauthFromMenu">Graph 重新授权</button>
          <div
            class="relative"
            @mouseenter="contextSubmenuOpen = true"
            @mouseleave="contextSubmenuOpen = false"
          >
            <button class="dropdown-item flex w-full items-center justify-between">
              <span>设置</span>
              <span class="text-xs text-gray-400">▶</span>
            </button>
            <div
              v-if="contextSubmenuOpen"
              class="dropdown absolute top-0 z-[80] w-80 p-3"
              :class="contextMenu.submenu_side === 'left' ? 'right-full mr-1' : 'left-full ml-1'"
            >
              <div class="space-y-3">
                <div>
                  <div class="mb-2 text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-dark-400">
                    移动到分组
                  </div>
                  <div class="grid grid-cols-2 gap-1.5">
                    <button
                      v-for="groupName in groupAssignmentOptions"
                      :key="groupName"
                      class="rounded-lg border border-gray-200 px-2 py-1.5 text-left text-xs hover:bg-gray-50 dark:border-dark-700 dark:hover:bg-dark-700/60"
                      @click="assignGroupFromMenu(groupName)"
                    >
                      {{ groupName }}
                    </button>
                  </div>
                </div>

                <div>
                  <div class="mb-2 text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-dark-400">
                    设置标签
                  </div>
                  <div class="grid max-h-32 grid-cols-2 gap-1.5 overflow-y-auto">
                    <button
                      v-for="tag in customTags"
                      :key="tag.name"
                      class="rounded-lg border border-gray-200 px-2 py-1.5 text-left text-xs hover:bg-gray-50 dark:border-dark-700 dark:hover:bg-dark-700/60"
                      @click="toggleTagFromMenu(tag.name)"
                    >
                      <span class="inline-flex items-center gap-1.5">
                        <span class="inline-block h-2 w-2 rounded-full" :style="{ backgroundColor: tag.color }"></span>
                        <span class="truncate">{{ accountHasTag(contextMenu.email, tag.name) ? '✓ ' : '' }}{{ tag.name }}</span>
                      </span>
                    </button>
                  </div>
                </div>

                <div>
                  <div class="mb-2 text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-dark-400">
                    旗标
                  </div>
                  <div class="grid grid-cols-4 gap-2">
                    <button
                      v-for="flag in flagOptions"
                      :key="flag.label"
                      class="flex flex-col items-center gap-1 rounded-lg border border-gray-200 px-2 py-2 text-[10px] hover:bg-gray-50 dark:border-dark-700 dark:hover:bg-dark-700/60"
                      @click="applyFlag(flag.color)"
                    >
                      <span
                        class="inline-block h-3.5 w-3.5 rounded-full"
                        :style="{ backgroundColor: flag.color || '#CBD5E1' }"
                      ></span>
                      <span class="truncate">{{ flag.label }}</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </template>

        <template v-else-if="contextMenu.kind === 'group'">
          <div class="px-3 py-2 text-xs font-semibold text-gray-500 dark:text-dark-400">分组操作</div>
          <button class="dropdown-item w-full" @click="openGroupEditor('edit')">编辑分组</button>
          <button class="dropdown-item w-full text-red-600 dark:text-red-400" @click="handleDeleteGroup">删除分组</button>
        </template>

        <template v-else-if="contextMenu.kind === 'tag'">
          <div class="px-3 py-2 text-xs font-semibold text-gray-500 dark:text-dark-400">标签操作</div>
          <button class="dropdown-item w-full" @click="openTagEditor('edit')">编辑标签</button>
          <button class="dropdown-item w-full text-red-600 dark:text-red-400" @click="handleDeleteTag">删除标签</button>
        </template>
      </div>

      <transition name="modal">
        <div v-if="detailDialog" class="modal-overlay" @click.self="detailDialog = null">
          <div class="modal-content max-w-2xl">
            <div class="modal-header">
              <div class="modal-title">{{ detailDialog.title }}</div>
              <button class="btn btn-secondary btn-sm px-2 py-1" @click="detailDialog = null">关闭</button>
            </div>
            <div class="modal-body">
              <pre class="mail-body">{{ detailDialog.body }}</pre>
            </div>
          </div>
        </div>
      </transition>

      <transition name="modal">
        <div v-if="taskCenterOpen" class="modal-overlay" @click.self="taskCenterOpen = false">
          <div class="modal-content max-w-4xl">
            <div class="modal-header">
              <div class="modal-title">任务中心</div>
              <div class="flex items-center gap-2">
                <button class="btn btn-secondary btn-sm px-2 py-1" @click="handleRunTokenRefresh">
                  立即全量刷新 Token
                </button>
                <button class="btn btn-secondary btn-sm px-2 py-1" @click="handleRunBackup">
                  立即备份账号
                </button>
                <button class="btn btn-secondary btn-sm px-2 py-1" @click="taskCenterOpen = false">关闭</button>
              </div>
            </div>
            <div class="modal-body grid gap-6 lg:grid-cols-2">
              <section class="card p-4">
                <h3 class="mb-3 text-sm font-semibold text-gray-900 dark:text-white">Token 刷新</h3>
                <label class="mb-3 inline-flex items-center gap-2 text-sm">
                  <input v-model="taskSettings.token_refresh_enabled" type="checkbox" />
                  启用定时 Token 刷新
                </label>
                <label class="block space-y-2">
                  <span class="text-xs text-gray-500 dark:text-dark-400">刷新间隔（分钟）</span>
                  <input v-model.number="taskSettings.token_refresh_interval_minutes" class="input" type="number" min="5" />
                </label>
              </section>

              <section class="card p-4">
                <h3 class="mb-3 text-sm font-semibold text-gray-900 dark:text-white">邮箱自动刷新</h3>
                <label class="mb-3 inline-flex items-center gap-2 text-sm">
                  <input v-model="taskSettings.auto_receive_enabled" type="checkbox" />
                  启用定时收件
                </label>
                <label class="block space-y-2">
                  <span class="text-xs text-gray-500 dark:text-dark-400">收件间隔（分钟）</span>
                  <input v-model.number="taskSettings.auto_receive_interval_minutes" class="input" type="number" min="5" />
                </label>
              </section>

              <section class="card p-4">
                <h3 class="mb-3 text-sm font-semibold text-gray-900 dark:text-white">自动备份</h3>
                <label class="mb-3 inline-flex items-center gap-2 text-sm">
                  <input v-model="taskSettings.backup_enabled" type="checkbox" />
                  启用定期备份
                </label>
                <div class="grid gap-3 md:grid-cols-2">
                  <label class="space-y-2">
                    <span class="text-xs text-gray-500 dark:text-dark-400">备份间隔（分钟）</span>
                    <input v-model.number="taskSettings.backup_interval_minutes" class="input" type="number" min="10" />
                  </label>
                  <label class="space-y-2">
                    <span class="text-xs text-gray-500 dark:text-dark-400">最大保留份数</span>
                    <input v-model.number="taskSettings.backup_keep_count" class="input" type="number" min="1" />
                  </label>
                </div>
                <label class="mt-3 block space-y-2">
                  <span class="text-xs text-gray-500 dark:text-dark-400">备份目录</span>
                  <input v-model="taskSettings.backup_directory" class="input" type="text" />
                </label>
              </section>

              <section class="card p-4">
                <div class="mb-3 flex items-center justify-between">
                  <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Token 刷新历史</h3>
                  <button class="btn btn-secondary btn-sm px-2 py-1" @click="loadTokenRefreshHistory">刷新历史</button>
                </div>
                <div class="max-h-80 space-y-2 overflow-y-auto">
                  <div
                    v-for="item in tokenRefreshHistory"
                    :key="item.id"
                    class="rounded-xl border border-gray-100 px-3 py-2 text-xs dark:border-dark-700"
                  >
                    <div class="flex items-center justify-between gap-2">
                      <span class="font-medium text-gray-900 dark:text-white">{{ item.created_at }}</span>
                      <span class="text-gray-500 dark:text-dark-400">{{ item.trigger_source }}</span>
                    </div>
                    <div class="mt-1 text-gray-500 dark:text-dark-400">
                      成功 {{ item.payload.success_count || 0 }} / 失败 {{ item.payload.failed_count || 0 }}
                    </div>
                  </div>
                  <div v-if="!tokenRefreshHistory.length" class="text-xs text-gray-500 dark:text-dark-400">
                    暂无刷新历史
                  </div>
                </div>
              </section>
            </div>
            <div class="modal-footer">
              <button class="btn btn-primary" @click="saveTaskCenterSettings">保存任务设置</button>
            </div>
          </div>
        </div>
      </transition>

      <transition name="modal">
        <div v-if="editAccountOpen" class="modal-overlay" @click.self="editAccountOpen = false">
          <div class="modal-content max-w-3xl">
            <div class="modal-header">
              <div class="modal-title">编辑账号</div>
              <button class="btn btn-secondary btn-sm px-2 py-1" @click="editAccountOpen = false">关闭</button>
            </div>
            <div class="modal-body grid gap-4 md:grid-cols-2">
              <label class="space-y-2">
                <span class="text-xs text-gray-500 dark:text-dark-400">邮箱</span>
                <input v-model="editAccountForm.email" class="input" type="email" />
              </label>
              <label class="space-y-2">
                <span class="text-xs text-gray-500 dark:text-dark-400">密码</span>
                <input v-model="editAccountForm.password" class="input" type="text" />
              </label>
              <label class="space-y-2 md:col-span-2">
                <span class="text-xs text-gray-500 dark:text-dark-400">Client ID / 第三段凭据</span>
                <input v-model="editAccountForm.auth_code_or_client_id" class="input" type="text" />
              </label>
              <label class="space-y-2 md:col-span-2">
                <span class="text-xs text-gray-500 dark:text-dark-400">Refresh Token / OAuth Token</span>
                <textarea v-model="editAccountForm.token" class="input min-h-28"></textarea>
              </label>
              <label class="space-y-2">
                <span class="text-xs text-gray-500 dark:text-dark-400">IMAP Host</span>
                <input v-model="editAccountForm.imap_host" class="input" type="text" />
              </label>
              <label class="space-y-2">
                <span class="text-xs text-gray-500 dark:text-dark-400">IMAP Port</span>
                <input v-model.number="editAccountForm.imap_port" class="input" type="number" min="1" />
              </label>
              <label class="space-y-2">
                <span class="text-xs text-gray-500 dark:text-dark-400">分组</span>
                <select v-model="editAccountForm.group_name" class="input">
                  <option value="未分组">未分组</option>
                  <option v-for="group in customGroups" :key="group.name" :value="group.name">
                    {{ group.name }}
                  </option>
                </select>
              </label>
              <label class="space-y-2">
                <span class="text-xs text-gray-500 dark:text-dark-400">旗标色</span>
                <input v-model="editAccountForm.flag_color" class="input" type="text" />
              </label>
              <div class="space-y-2 md:col-span-2">
                <span class="text-xs text-gray-500 dark:text-dark-400">标签</span>
                <div class="flex flex-wrap gap-2 rounded-xl border border-gray-200 p-3 dark:border-dark-700">
                  <label
                    v-for="tag in customTags"
                    :key="tag.name"
                    class="inline-flex items-center gap-1.5 text-xs"
                  >
                    <input v-model="editAccountForm.tags" :value="tag.name" type="checkbox" />
                    <span class="inline-block h-2 w-2 rounded-full" :style="{ backgroundColor: tag.color }"></span>
                    {{ tag.name }}
                  </label>
                </div>
              </div>
            </div>
            <div class="modal-footer">
              <button class="btn btn-primary" @click="handleSaveAccountEdit">保存账号</button>
            </div>
          </div>
        </div>
      </transition>

      <transition name="modal">
        <div v-if="taxonomyDialog.open" class="modal-overlay" @click.self="taxonomyDialog.open = false">
          <div class="modal-content max-w-xl">
            <div class="modal-header">
              <div class="modal-title">{{ taxonomyDialog.type === 'group' ? '分组' : '标签' }}{{ taxonomyDialog.mode === 'create' ? '新增' : '编辑' }}</div>
              <button class="btn btn-secondary btn-sm px-2 py-1" @click="taxonomyDialog.open = false">关闭</button>
            </div>
            <div class="modal-body grid gap-4">
              <label class="space-y-2">
                <span class="text-xs text-gray-500 dark:text-dark-400">名称</span>
                <input v-model="taxonomyDialog.form.name" class="input" type="text" />
              </label>
              <label class="space-y-2">
                <span class="text-xs text-gray-500 dark:text-dark-400">颜色</span>
                <div class="flex items-center gap-3">
                  <input v-model="taxonomyDialog.form.color" class="h-10 w-14 rounded-lg border border-gray-200 bg-transparent p-1 dark:border-dark-700" type="color" />
                  <div class="grid flex-1 grid-cols-6 gap-2">
                    <button
                      v-for="color in colorPresets"
                      :key="color"
                      class="h-8 rounded-lg border-2"
                      :class="taxonomyDialog.form.color === color ? 'border-gray-900 dark:border-white' : 'border-transparent'"
                      :style="{ backgroundColor: color }"
                      @click="taxonomyDialog.form.color = color"
                    ></button>
                  </div>
                </div>
              </label>
              <label class="space-y-2">
                <span class="text-xs text-gray-500 dark:text-dark-400">优先级（1-999）</span>
                <input v-model.number="taxonomyDialog.form.priority" class="input" type="number" min="1" max="999" />
              </label>
            </div>
            <div class="modal-footer">
              <button class="btn btn-primary" @click="saveTaxonomyDialog">保存</button>
            </div>
          </div>
        </div>
      </transition>

      <transition name="modal">
        <div v-if="confirmDialog.open" class="modal-overlay" @click.self="closeConfirmDialog">
          <div class="modal-content max-w-md">
            <div class="modal-header">
              <div class="modal-title">{{ confirmDialog.title }}</div>
              <button class="btn btn-secondary btn-sm px-2 py-1" @click="closeConfirmDialog">关闭</button>
            </div>
            <div class="modal-body">
              <p class="text-sm leading-7 text-gray-600 dark:text-dark-300">{{ confirmDialog.message }}</p>
            </div>
            <div class="modal-footer">
              <button class="btn btn-secondary" @click="closeConfirmDialog">取消</button>
              <button class="btn btn-danger" @click="confirmDialogAction">确认</button>
            </div>
          </div>
        </div>
      </transition>

      <transition name="modal">
        <div v-if="importDialogOpen" class="modal-overlay" @click.self="importDialogOpen = false">
          <div class="modal-content max-w-2xl">
            <div class="modal-header">
              <div class="modal-title">导入账号</div>
              <button class="btn btn-secondary btn-sm px-2 py-1" @click="importDialogOpen = false">关闭</button>
            </div>
            <div class="modal-body space-y-4">
              <div class="tabs">
                <button class="tab" :class="{ 'tab-active': importMode === 'text' }" @click="importMode = 'text'">粘贴文本</button>
                <button class="tab" :class="{ 'tab-active': importMode === 'file' }" @click="importMode = 'file'">选择文件</button>
              </div>

              <div v-if="importMode === 'text'" class="space-y-2">
                <textarea
                  v-model="importText"
                  class="input min-h-64 font-mono text-xs"
                  placeholder="每行一个账号，例如：email || password || client_id || refresh_token"
                ></textarea>
              </div>

              <div v-else class="space-y-3">
                <button class="btn btn-secondary" @click="fileInput?.click()">选择 TXT 文件</button>
                <div class="text-sm text-gray-500 dark:text-dark-400">
                  {{ selectedImportFileName || '尚未选择文件' }}
                </div>
              </div>
            </div>
            <div class="modal-footer">
              <button class="btn btn-primary" @click="submitImport">开始导入</button>
            </div>
          </div>
        </div>
      </transition>

      <transition name="modal">
        <div v-if="graphReauthDialog.open" class="modal-overlay" @click.self="closeGraphReauthDialog">
          <div class="modal-content max-w-xl">
            <div class="modal-header">
              <div class="modal-title">Graph 重新授权</div>
              <button class="btn btn-secondary btn-sm px-2 py-1" @click="closeGraphReauthDialog">关闭</button>
            </div>
            <div class="modal-body space-y-4">
              <div class="text-sm text-gray-600 dark:text-dark-300">
                当前账号：{{ graphReauthDialog.email || '-' }}
              </div>
              <div
                v-if="graphReauthDialog.user_code"
                class="rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-dark-700 dark:bg-dark-800/70"
              >
                <div class="text-xs text-gray-500 dark:text-dark-400">微软验证码</div>
                <div class="mt-1 text-2xl font-semibold tracking-[0.25em] text-gray-900 dark:text-white">
                  {{ graphReauthDialog.user_code }}
                </div>
                <div class="mt-3 text-xs text-gray-500 dark:text-dark-400 break-all">
                  {{ graphReauthDialog.verification_uri }}
                </div>
              </div>
              <div class="text-sm text-gray-600 dark:text-dark-300">
                {{ graphReauthDialog.message || '请按提示完成微软授权。' }}
              </div>
              <div class="text-xs text-gray-500 dark:text-dark-400">
                状态：{{ graphReauthStatusLabel }} · 剩余 {{ graphReauthDialog.expires_in }} 秒
              </div>
            </div>
            <div class="modal-footer">
              <button class="btn btn-secondary" @click="copyGraphUserCode">复制验证码</button>
              <a
                v-if="graphReauthDialog.verification_uri"
                class="btn btn-secondary"
                :href="graphReauthDialog.verification_uri"
                target="_blank"
                rel="noreferrer"
              >
                打开微软授权页
              </a>
              <button class="btn btn-primary" @click="pollGraphReauth(true)">立即检查结果</button>
            </div>
          </div>
        </div>
      </transition>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import {
  assignAccountGroup,
  createGroupDetailed,
  createTag,
  deleteAccounts,
  deleteGroup,
  deleteTag,
  exportAccounts,
  getAccountDetail,
  getBodyStatus,
  getDashboardState,
  getGraphReauthStatus,
  getTokenRefreshHistory,
  importAccounts,
  openMail,
  receiveAccounts,
  reloginAccounts,
  runAccountBackup,
  runTokenRefresh,
  saveSettings,
  setAccountTags,
  startGraphReauth,
  toggleMailStar,
  updateAccount,
  updateGroup,
  updateTag,
  updateFlag,
} from '@/api/dashboard'
import Icon from '@/components/common/Icon.vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import { useToastStore } from '@/stores/toast'
import type {
  AccountIssue,
  BodyTask,
  DashboardState,
  GroupDefinition,
  HeaderMetric,
  MailAccountSummary,
  MailItem,
  TagDefinition,
} from '@/types'

type GroupOption = {
  key: string
  label: string
  accountCount: number
  color: string
  priority: number
}

type TagOption = {
  key: string
  label: string
  accountCount: number
  color: string
  priority: number
}

const dashboard = ref<DashboardState | null>(null)
const selectedGroupKey = ref('未分组')
const selectedTagKey = ref('')
const selectedAccountEmail = ref<string | null>(null)
const selectedMailKey = ref('')
const selectedMailDetail = ref<MailItem | null>(null)
const selectedBodyTask = ref<BodyTask | null>(null)
const checkedAccounts = ref<string[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const toastStore = useToastStore()
const detailDialog = ref<{ title: string; body: string } | null>(null)
const groupSectionOpen = ref(true)
const tagSectionOpen = ref(true)
const taskCenterOpen = ref(false)
const taskSettingsDirty = ref(false)
const editAccountOpen = ref(false)
const importDialogOpen = ref(false)
const importMode = ref<'text' | 'file'>('text')
const importText = ref('')
const selectedImportFile = ref<File | null>(null)
const selectedImportFileName = ref('')
const graphReauthDialog = ref({
  open: false,
  email: '',
  session_id: '',
  user_code: '',
  verification_uri: '',
  expires_in: 0,
  interval: 5,
  status: 'pending',
  message: '',
})
const accountPage = ref(1)
const mailPage = ref(1)
const accountPageSize = ref(10)
const mailPageSize = ref(10)
const accountListRef = ref<HTMLElement | null>(null)
const mailListRef = ref<HTMLElement | null>(null)
const contextSubmenuOpen = ref(false)
const contextMenu = ref({
  visible: false,
  x: 0,
  y: 0,
  kind: 'account' as 'account' | 'group' | 'tag',
  email: '',
  name: '',
  submenu_side: 'right' as 'right' | 'left',
})
const searchTerm = ref('')
const colorPresets = [
  '#D6EAF8',
  '#BFDBFE',
  '#93C5FD',
  '#60A5FA',
  '#38BDF8',
  '#22D3EE',
  '#34D399',
  '#A3E635',
  '#FACC15',
  '#FB923C',
  '#F87171',
  '#C084FC',
]
const tokenRefreshHistory = ref<
  Array<{
    id: number
    created_at: string
    trigger_source: string
    payload: Record<string, any>
  }>
>([])
const taskSettings = ref({
  token_refresh_enabled: false,
  token_refresh_interval_minutes: 360,
  auto_receive_enabled: false,
  auto_receive_interval_minutes: 15,
  backup_enabled: false,
  backup_interval_minutes: 1440,
  backup_directory: 'backups',
  backup_keep_count: 10,
})
const editAccountForm = ref({
  original_email: '',
  email: '',
  password: '',
  auth_code_or_client_id: '',
  token: '',
  imap_host: 'imap-mail.outlook.com',
  imap_port: 993,
  group_name: '未分组',
  flag_color: '',
  tags: [] as string[],
})
const taxonomyDialog = ref({
  open: false,
  type: 'group' as 'group' | 'tag',
  mode: 'create' as 'create' | 'edit',
  original_name: '',
  form: {
    name: '',
    color: '#D6EAF8',
    priority: 100,
  },
})
const confirmDialog = ref({
  open: false,
  title: '',
  message: '',
})
let pendingConfirmAction: null | (() => Promise<void> | void) = null

const flagOptions = [
  { label: '红旗', color: '#EF4444' },
  { label: '橙旗', color: '#F97316' },
  { label: '黄旗', color: '#EAB308' },
  { label: '绿旗', color: '#22C55E' },
  { label: '蓝旗', color: '#3B82F6' },
  { label: '紫旗', color: '#A855F7' },
  { label: '清除旗子', color: '' },
]

let refreshTimer: number | null = null
let bodyTimer: number | null = null
let graphReauthTimer: number | null = null
let accountResizeObserver: ResizeObserver | null = null
let mailResizeObserver: ResizeObserver | null = null
let handleWindowResize: (() => void) | null = null

const allAccounts = computed(() => dashboard.value?.accounts || [])
const allMails = computed(() => dashboard.value?.mails || [])
const customGroups = computed<GroupDefinition[]>(() => dashboard.value?.settings.custom_groups || [])
const customTags = computed<TagDefinition[]>(() => dashboard.value?.settings.custom_tags || [])

const groupOptions = computed<GroupOption[]>(() => {
  const options: GroupOption[] = []
  const accounts = allAccounts.value
  const groupDefs: GroupDefinition[] = [
    { name: '未分组', color: '#D6EAF8', priority: 1000 },
    ...customGroups.value,
  ]

  options.push({
    key: '__all__',
    label: '全部',
    accountCount: accounts.length,
    color: '#CBD5E1',
    priority: 2000,
  })

  groupDefs.forEach((groupDef) => {
    const accountsInGroup = accounts.filter((account) => (account.group_name || '未分组') === groupDef.name)
    options.push({
      key: groupDef.name,
      label: groupDef.name,
      accountCount: accountsInGroup.length,
      color: groupDef.color,
      priority: groupDef.priority,
    })
  })

  const starredMails = allMails.value.filter((mail) => mail.is_starred)
  options.push({
    key: '__starred__',
    label: '星标',
    accountCount: new Set(starredMails.map((mail) => mail.account_email)).size,
    color: '#FBBF24',
    priority: 1500,
  })

  return options
})

const tagOptions = computed<TagOption[]>(() =>
  customTags.value.map((tagDef) => ({
    key: tagDef.name,
    label: tagDef.name,
    accountCount: allAccounts.value.filter((account) => account.tags.includes(tagDef.name)).length,
    color: tagDef.color,
    priority: tagDef.priority,
  })),
)

const selectedGroupLabel = computed(
  () => groupOptions.value.find((group) => group.key === selectedGroupKey.value)?.label || '未分组',
)

const starredAccountEmails = computed(() => {
  return new Set(allMails.value.filter((mail) => mail.is_starred).map((mail) => mail.account_email))
})

const visibleAccountsAll = computed(() => {
  let accounts = allAccounts.value
  if (selectedGroupKey.value === '__starred__') {
    accounts = accounts.filter((account) => starredAccountEmails.value.has(account.email))
  } else if (selectedGroupKey.value !== '__all__') {
    accounts = accounts.filter(
      (account) => (account.group_name || '未分组') === selectedGroupKey.value,
    )
  }
  if (selectedTagKey.value) {
    accounts = accounts.filter((account) => account.tags.includes(selectedTagKey.value))
  }
  const query = searchTerm.value.trim().toLowerCase()
  if (query) {
    accounts = accounts.filter(
      (account) =>
        account.email.toLowerCase().includes(query) ||
        (account.group_name || '').toLowerCase().includes(query) ||
        (account.status || '').toLowerCase().includes(query),
    )
  }
  return accounts
})

const visibleMailsAll = computed(() => {
  let mails = allMails.value
  if (selectedGroupKey.value === '__starred__') {
    mails = mails.filter((mail) => mail.is_starred)
  }
  const allowedEmails = new Set(visibleAccountsAll.value.map((account) => account.email))
  mails = mails.filter((mail) => allowedEmails.has(mail.account_email))
  if (selectedAccountEmail.value) {
    mails = mails.filter((mail) => mail.account_email === selectedAccountEmail.value)
  }
  const query = searchTerm.value.trim().toLowerCase()
  if (query) {
    mails = mails.filter(
      (mail) =>
        mail.account_email.toLowerCase().includes(query) ||
        mail.subject.toLowerCase().includes(query) ||
        mail.from_text.toLowerCase().includes(query),
    )
  }
  return mails
})

const totalAccountPages = computed(() =>
  Math.max(1, Math.ceil(visibleAccountsAll.value.length / accountPageSize.value)),
)
const totalMailPages = computed(() => Math.max(1, Math.ceil(visibleMailsAll.value.length / mailPageSize.value)))

const paginatedAccounts = computed(() => {
  const start = (accountPage.value - 1) * accountPageSize.value
  return visibleAccountsAll.value.slice(start, start + accountPageSize.value)
})

const paginatedMails = computed(() => {
  const start = (mailPage.value - 1) * mailPageSize.value
  return visibleMailsAll.value.slice(start, start + mailPageSize.value)
})

const groupedMails = computed(() => {
  const mails = paginatedMails.value
  const today = new Date().toISOString().slice(0, 10)
  const groups = [
    { label: '今日', items: [] as MailItem[] },
    { label: '更早（7天内）', items: [] as MailItem[] },
    { label: '7天以前', items: [] as MailItem[] },
  ]

  mails.forEach((mail) => {
    const dateValue = new Date(mail.date_value)
    if (mail.date_text.startsWith(today)) {
      groups[0].items.push(mail)
      return
    }
    if (Date.now() - dateValue.getTime() <= 7 * 24 * 60 * 60 * 1000) {
      groups[1].items.push(mail)
      return
    }
    groups[2].items.push(mail)
  })

  return groups.filter((group) => group.items.length > 0)
})

const nonSuccessAccounts = computed<AccountIssue[]>(() =>
  allAccounts.value
    .filter((account) => account.status !== '登录成功')
    .map((account) => ({
      email: account.email,
      status: account.status,
      last_error_summary: account.last_error_summary,
      last_error: account.last_error,
    })),
)

const queueDetails = computed(() => dashboard.value?.overview.queue || null)

const headerMetrics = computed<HeaderMetric[]>(() => [
  {
    icon: 'mail',
    label: '邮箱',
    value: dashboard.value?.overview.total_accounts ?? 0,
  },
  {
    key: 'success',
    icon: 'shield',
    label: '成功',
    value: dashboard.value?.overview.success_accounts ?? 0,
    clickable: true,
  },
  {
    icon: 'inbox',
    label: '未读',
    value: dashboard.value?.overview.unread_mails ?? 0,
  },
  {
    key: 'queue',
    icon: 'refresh',
    label: '队列',
    value: `${dashboard.value?.overview.queue.percent ?? 0}%`,
    clickable: true,
  },
])

const hasSelection = computed(() => checkedAccounts.value.length > 0)
const allChecked = computed(() => {
  const accounts = visibleAccountsAll.value
  return accounts.length > 0 && checkedAccounts.value.length === accounts.length
})

const selectedAccount = computed(() =>
  allAccounts.value.find((item) => item.email === selectedAccountEmail.value) || null,
)

const groupAssignmentOptions = computed(() => ['未分组', ...customGroups.value.map((item) => item.name)])

const bodyProgress = computed(() => {
  const task = selectedBodyTask.value
  if (!task) return 0
  if (task.state === 'done') return 100
  if (task.total <= 0) return task.state === 'queued' ? 5 : 0
  return Math.min(100, Math.round((task.downloaded / task.total) * 100))
})

const bodyStatusText = computed(() => {
  const task = selectedBodyTask.value
  if (!selectedMailKey.value) return '等待选择邮件'
  if (!task) return '等待任务'
  if (task.state === 'downloading' && task.total > 0) {
    return `正在下载正文: ${(task.downloaded / 1024).toFixed(1)}/${(task.total / 1024).toFixed(1)} KB · ${task.speed_kb_s.toFixed(1)} KB/s`
  }
  if (task.state === 'queued') return '等待下载正文...'
  if (task.state === 'error') return `正文下载失败: ${task.status}`
  if (task.state === 'done') return '正文已缓存'
  return task.status || '等待任务'
})

const graphReauthStatusLabel = computed(() => {
  if (graphReauthDialog.value.status === 'completed') return '已完成'
  if (graphReauthDialog.value.status === 'failed') return '失败'
  if (graphReauthDialog.value.status === 'expired') return '已过期'
  return '等待授权'
})

watch(
  () => groupOptions.value.map((group) => group.key),
  (keys) => {
    if (!keys.includes(selectedGroupKey.value)) {
      selectedGroupKey.value = '未分组'
    }
  },
  { immediate: true },
)

watch(
  visibleAccountsAll,
  (accounts) => {
    if (selectedAccountEmail.value && !accounts.some((account) => account.email === selectedAccountEmail.value)) {
      selectedAccountEmail.value = null
    }
    checkedAccounts.value = checkedAccounts.value.filter((email) =>
      accounts.some((account) => account.email === email),
    )
  },
  { immediate: true },
)

watch(
  visibleMailsAll,
  (mails) => {
    if (selectedMailKey.value && !mails.some((mail) => mail.local_key === selectedMailKey.value)) {
      selectedMailKey.value = ''
      selectedMailDetail.value = null
      selectedBodyTask.value = null
      stopBodyPolling()
    }
  },
  { immediate: true },
)

watch(
  [selectedGroupKey, selectedTagKey, selectedAccountEmail],
  () => {
    accountPage.value = 1
    mailPage.value = 1
  },
)

watch(
  taskSettings,
  () => {
    if (taskCenterOpen.value) {
      taskSettingsDirty.value = true
    }
  },
  { deep: true },
)

watch(totalAccountPages, (value) => {
  if (accountPage.value > value) {
    accountPage.value = value
  }
})

watch(totalMailPages, (value) => {
  if (mailPage.value > value) {
    mailPage.value = value
  }
})

onMounted(async () => {
  await refreshState()
  refreshTimer = window.setInterval(() => {
    refreshState(true)
  }, 4000)
  document.addEventListener('click', closeContextMenu)
  setupAutoPageSizing()
})

onBeforeUnmount(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
  stopBodyPolling()
  stopGraphReauthPolling()
  document.removeEventListener('click', closeContextMenu)
  accountResizeObserver?.disconnect()
  mailResizeObserver?.disconnect()
  if (handleWindowResize) {
    window.removeEventListener('resize', handleWindowResize)
  }
})

function computePageSize(containerHeight: number, rowHeight: number, minimum = 4) {
  return Math.max(minimum, Math.floor(containerHeight / rowHeight))
}

function setupAutoPageSizing() {
  const refreshSizes = () => {
    if (accountListRef.value) {
      accountPageSize.value = computePageSize(accountListRef.value.clientHeight - 4, 70, 5)
    }
    if (mailListRef.value) {
      mailPageSize.value = computePageSize(mailListRef.value.clientHeight - 18, 66, 6)
    }
  }

  refreshSizes()
  accountResizeObserver = new ResizeObserver(refreshSizes)
  mailResizeObserver = new ResizeObserver(refreshSizes)
  if (accountListRef.value) accountResizeObserver.observe(accountListRef.value)
  if (mailListRef.value) mailResizeObserver.observe(mailListRef.value)
  handleWindowResize = refreshSizes
  window.addEventListener('resize', handleWindowResize)
}

async function refreshState(silent = false) {
  try {
    const response = await getDashboardState()
    dashboard.value = response.data
    if (!taskCenterOpen.value || !taskSettingsDirty.value) {
      taskSettings.value = {
        token_refresh_enabled: response.data.settings.token_refresh_enabled,
        token_refresh_interval_minutes: response.data.settings.token_refresh_interval_minutes,
        auto_receive_enabled: response.data.settings.auto_receive_enabled,
        auto_receive_interval_minutes: response.data.settings.auto_receive_interval_minutes,
        backup_enabled: response.data.settings.backup_enabled,
        backup_interval_minutes: response.data.settings.backup_interval_minutes,
        backup_directory: response.data.settings.backup_directory,
        backup_keep_count: response.data.settings.backup_keep_count,
      }
    }
    if (selectedMailKey.value) {
      const current = response.data.mails.find((item) => item.local_key === selectedMailKey.value)
      if (current) {
        selectedMailDetail.value = current
      }
    }
  } catch (error: any) {
    if (!silent) {
      showError(error?.response?.data?.detail || '加载后台数据失败')
    }
  }
}

function showSuccess(message: string) {
  toastStore.push(message, 'success')
}

function showError(message: string) {
  toastStore.push(message, 'error')
}

function openConfirmDialog(title: string, message: string, action: () => Promise<void> | void) {
  confirmDialog.value = { open: true, title, message }
  pendingConfirmAction = action
}

function closeConfirmDialog() {
  confirmDialog.value.open = false
  pendingConfirmAction = null
}

async function confirmDialogAction() {
  const action = pendingConfirmAction
  closeConfirmDialog()
  if (action) {
    await action()
  }
}

function tagColor(tagName: string) {
  return customTags.value.find((item) => item.name === tagName)?.color || '#BFDBFE'
}

function tagPillStyle(tagName: string) {
  const color = tagColor(tagName)
  return {
    backgroundColor: `${color}22`,
    color: '#334155',
    border: `1px solid ${color}55`,
  }
}

function visibleAccountTags(account: MailAccountSummary) {
  return account.tags.slice(0, 2)
}

function accountHasTag(email: string, tagName: string) {
  return allAccounts.value.find((item) => item.email === email)?.tags.includes(tagName) || false
}

function folderBadgeClass(folderName: string) {
  if (folderName === '收件箱') return 'badge-primary'
  if (folderName === '垃圾邮件') return 'badge-warning'
  if (folderName === '已删除') return 'badge-gray'
  return 'badge-gray'
}

function formatErrorDetail(errorText: string) {
  if (!errorText) return '暂无错误详情'
  return errorText.replaceAll('；', '\n').replaceAll('\\n', '\n')
}

function handleShowAccountDetail(account: AccountIssue) {
  detailDialog.value = {
    title: `${account.email} · ${account.status}`,
    body: formatErrorDetail(account.last_error || account.last_error_summary),
  }
}

function openAccountDetail(account: MailAccountSummary) {
  handleShowAccountDetail({
    email: account.email,
    status: account.status,
    last_error_summary: account.last_error_summary,
    last_error: account.last_error,
  })
}

function triggerImport() {
  importDialogOpen.value = true
  importMode.value = 'text'
  importText.value = ''
  selectedImportFile.value = null
  selectedImportFileName.value = ''
}

function stopGraphReauthPolling() {
  if (graphReauthTimer) {
    window.clearInterval(graphReauthTimer)
    graphReauthTimer = null
  }
}

function closeGraphReauthDialog() {
  graphReauthDialog.value.open = false
  stopGraphReauthPolling()
}

async function copyGraphUserCode() {
  const code = graphReauthDialog.value.user_code
  if (!code) return
  try {
    await navigator.clipboard.writeText(code)
    showSuccess(`已复制验证码: ${code}`)
  } catch {
    showError('复制验证码失败')
  }
}

async function openGraphReauthFromMenu() {
  const email = contextMenu.value.email
  closeContextMenu()
  try {
    const response = await startGraphReauth(email)
    graphReauthDialog.value = {
      open: true,
      email: response.data.email,
      session_id: response.data.session_id,
      user_code: response.data.user_code,
      verification_uri: response.data.verification_uri,
      expires_in: response.data.expires_in,
      interval: response.data.interval,
      status: response.data.status,
      message: response.data.message,
    }
    stopGraphReauthPolling()
    graphReauthTimer = window.setInterval(() => {
      pollGraphReauth()
    }, Math.max(3000, response.data.interval * 1000))
  } catch (error: any) {
    showError(error?.response?.data?.detail || 'Graph 重新授权启动失败')
  }
}

async function pollGraphReauth(manual = false) {
  const sessionId = graphReauthDialog.value.session_id
  if (!sessionId) return
  try {
    const response = await getGraphReauthStatus(sessionId)
    graphReauthDialog.value = {
      ...graphReauthDialog.value,
      ...response.data,
      open: true,
    }
    if (response.data.status === 'completed') {
      stopGraphReauthPolling()
      showSuccess(response.data.message || 'Graph 重新授权成功')
      await refreshState(true)
      return
    }
    if (response.data.status === 'failed' || response.data.status === 'expired') {
      stopGraphReauthPolling()
      showError(response.data.message || 'Graph 重新授权失败')
      return
    }
    if (manual) {
      showSuccess(response.data.message || '授权尚未完成，请继续在微软页面操作')
    }
  } catch (error: any) {
    if (manual) {
      showError(error?.response?.data?.detail || 'Graph 授权状态检查失败')
    }
  }
}

async function openTaskCenter() {
  taskCenterOpen.value = true
  taskSettingsDirty.value = false
  await loadTokenRefreshHistory()
}

async function loadTokenRefreshHistory() {
  try {
    const response = await getTokenRefreshHistory()
    tokenRefreshHistory.value = response.data.items
  } catch (error: any) {
    showError(error?.response?.data?.detail || '加载刷新历史失败')
  }
}

async function saveTaskCenterSettings() {
  if (!dashboard.value) return
  try {
    const response = await saveSettings({
      ...dashboard.value.settings,
      ...taskSettings.value,
    })
    dashboard.value.settings = response.data
    taskSettings.value = {
      token_refresh_enabled: response.data.token_refresh_enabled,
      token_refresh_interval_minutes: response.data.token_refresh_interval_minutes,
      auto_receive_enabled: response.data.auto_receive_enabled,
      auto_receive_interval_minutes: response.data.auto_receive_interval_minutes,
      backup_enabled: response.data.backup_enabled,
      backup_interval_minutes: response.data.backup_interval_minutes,
      backup_directory: response.data.backup_directory,
      backup_keep_count: response.data.backup_keep_count,
    }
    taskSettingsDirty.value = false
    showSuccess(response.message)
  } catch (error: any) {
    showError(error?.response?.data?.detail || '保存任务设置失败')
  }
}

async function handleRunTokenRefresh() {
  try {
    const response = await runTokenRefresh()
    showSuccess(response.message)
    await loadTokenRefreshHistory()
    await refreshState(true)
  } catch (error: any) {
    showError(error?.response?.data?.detail || 'Token 刷新失败')
  }
}

async function handleRunBackup() {
  try {
    const response = await runAccountBackup()
    showSuccess(`${response.message}：${response.data.path}`)
  } catch (error: any) {
    showError(error?.response?.data?.detail || '账号备份失败')
  }
}

async function handleImportFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  selectedImportFile.value = file
  selectedImportFileName.value = file.name
  importMode.value = 'file'
  input.value = ''
}

async function submitImport() {
  try {
    let payloadFile: File | null = null
    if (importMode.value === 'text') {
      if (!importText.value.trim()) {
        showError('请输入账号文本')
        return
      }
      payloadFile = new File([importText.value], 'accounts.txt', { type: 'text/plain' })
    } else {
      payloadFile = selectedImportFile.value
      if (!payloadFile) {
        showError('请选择 TXT 文件')
        return
      }
    }
    const response = await importAccounts(payloadFile)
    showSuccess(response.message)
    importDialogOpen.value = false
    await refreshState(true)
  } catch (error: any) {
    showError(error?.response?.data?.detail || '导入失败')
  }
}

async function handleCreateGroup() {
  taxonomyDialog.value = {
    open: true,
    type: 'group',
    mode: 'create',
    original_name: '',
    form: { name: '', color: '#D6EAF8', priority: 100 },
  }
}

async function handleCreateTag() {
  taxonomyDialog.value = {
    open: true,
    type: 'tag',
    mode: 'create',
    original_name: '',
    form: { name: '', color: '#BFDBFE', priority: 100 },
  }
}

async function handleExportAccounts() {
  try {
    const exportEmails =
      checkedAccounts.value.length > 0
        ? checkedAccounts.value
        : selectedGroupKey.value === '__starred__'
          ? visibleAccountsAll.value.map((account) => account.email)
          : undefined
    const response = await exportAccounts({
      groupName: selectedGroupKey.value,
      emails: exportEmails,
    })
    const blob = new Blob([response.data], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'easymail-export.txt'
    anchor.click()
    URL.revokeObjectURL(url)
    showSuccess('邮箱导出完成')
  } catch (error: any) {
    showError(error?.response?.data?.detail || '邮箱导出失败')
  }
}

function selectGroup(groupKey: string) {
  selectedGroupKey.value = groupKey
  if (groupKey === '__all__') {
    selectedAccountEmail.value = null
  }
}

function selectTag(tagKey: string) {
  selectedTagKey.value = tagKey
}

function toggleAccount(email: string, checked: boolean) {
  checkedAccounts.value = checked
    ? Array.from(new Set([...checkedAccounts.value, email]))
    : checkedAccounts.value.filter((item) => item !== email)
}

function toggleAllAccounts(checked: boolean) {
  checkedAccounts.value = checked ? visibleAccountsAll.value.map((item) => item.email) : []
}

async function filterAccount(email: string) {
  selectedAccountEmail.value = email
}

async function filterAllMails() {
  selectedAccountEmail.value = null
}

function openGroupContextMenu(event: MouseEvent, group: GroupOption) {
  if (group.key === '__all__' || group.key === '__starred__' || group.key === '未分组') return
  contextMenu.value = {
    visible: true,
    x: Math.min(event.clientX, window.innerWidth - 280),
    y: Math.min(event.clientY, window.innerHeight - 260),
    kind: 'group',
    email: '',
    name: group.key,
    submenu_side: 'right',
  }
}

function openTagContextMenu(event: MouseEvent, tag: TagOption) {
  contextMenu.value = {
    visible: true,
    x: Math.min(event.clientX, window.innerWidth - 280),
    y: Math.min(event.clientY, window.innerHeight - 260),
    kind: 'tag',
    email: '',
    name: tag.key,
    submenu_side: 'right',
  }
}

function statusTextClass(status: string) {
  if (status === '登录成功') return 'text-sky-600 dark:text-sky-400'
  if (status === '登录失败' || status === '收信失败') return 'text-red-500 dark:text-red-400'
  if (status === '收信中' || status === '登录中') return 'text-blue-500 dark:text-blue-400'
  return 'text-gray-900 dark:text-white'
}

async function handleOpenMail(mail: MailItem) {
  selectedMailKey.value = mail.local_key
  try {
    const response = await openMail(mail.local_key)
    selectedMailDetail.value = response.data.mail
    selectedBodyTask.value = response.data.body_task
    if (
      selectedBodyTask.value.state === 'queued' ||
      selectedBodyTask.value.state === 'downloading'
    ) {
      startBodyPolling(mail.local_key)
    } else {
      stopBodyPolling()
    }
    await refreshState(true)
  } catch (error: any) {
    showError(error?.response?.data?.detail || '打开邮件失败')
  }
}

async function handleToggleStar(mail: MailItem) {
  try {
    const response = await toggleMailStar(mail.local_key, !mail.is_starred)
    showSuccess(response.message)
    if (selectedMailDetail.value?.local_key === mail.local_key) {
      selectedMailDetail.value.is_starred = response.data.is_starred
    }
    await refreshState(true)
  } catch (error: any) {
    showError(error?.response?.data?.detail || '星标更新失败')
  }
}

function startBodyPolling(localKey: string) {
  stopBodyPolling()
  bodyTimer = window.setInterval(async () => {
    try {
      const response = await getBodyStatus(localKey)
      selectedMailDetail.value = response.data.mail
      selectedBodyTask.value = response.data.body_task
      if (['done', 'error', 'idle'].includes(response.data.body_task.state)) {
        stopBodyPolling()
        await refreshState(true)
      }
    } catch {
      stopBodyPolling()
    }
  }, 900)
}

function stopBodyPolling() {
  if (bodyTimer) {
    window.clearInterval(bodyTimer)
    bodyTimer = null
  }
}

async function refreshMailBody() {
  if (!selectedMailDetail.value) return
  await handleOpenMail(selectedMailDetail.value)
}

async function handleReceiveAll() {
  try {
    const response = await receiveAccounts({ emails: [], include_all: true })
    showSuccess(response.message)
    await refreshState(true)
  } catch (error: any) {
    showError(error?.response?.data?.detail || '收件失败')
  }
}

async function handleReceiveChecked() {
  try {
    const response = await receiveAccounts({ emails: checkedAccounts.value })
    showSuccess(response.message)
    await refreshState(true)
  } catch (error: any) {
    showError(error?.response?.data?.detail || '收件失败')
  }
}

async function handleReloginChecked() {
  try {
    const response = await reloginAccounts({ emails: checkedAccounts.value })
    showSuccess(response.message)
    await refreshState(true)
  } catch (error: any) {
    showError(error?.response?.data?.detail || '重新登录失败')
  }
}

async function handleDeleteChecked() {
  if (!checkedAccounts.value.length) return
  openConfirmDialog(
    '删除邮箱',
    `确定删除 ${checkedAccounts.value.length} 个邮箱及其本地缓存吗？`,
    async () => {
      try {
        const response = await deleteAccounts(checkedAccounts.value)
        checkedAccounts.value = []
        selectedMailKey.value = ''
        selectedMailDetail.value = null
        selectedBodyTask.value = null
        showSuccess(response.message)
        await refreshState(true)
      } catch (error: any) {
        showError(error?.response?.data?.detail || '删除失败')
      }
    },
  )
}

function openContextMenu(event: MouseEvent, email: string) {
  contextMenu.value = {
    visible: true,
    x: Math.min(event.clientX, window.innerWidth - 280),
    y: Math.min(event.clientY, window.innerHeight - 420),
    kind: 'account',
    email,
    name: '',
    submenu_side: event.clientX > window.innerWidth - 430 ? 'left' : 'right',
  }
  contextSubmenuOpen.value = false
}

function closeContextMenu() {
  contextMenu.value.visible = false
  contextSubmenuOpen.value = false
}

async function openEditAccountFromMenu() {
  const email = contextMenu.value.email
  closeContextMenu()
  try {
    const response = await getAccountDetail(email)
    editAccountForm.value = {
      original_email: email,
      ...response.data.account,
    }
    editAccountOpen.value = true
  } catch (error: any) {
    showError(error?.response?.data?.detail || '读取账号详情失败')
  }
}

async function handleSaveAccountEdit() {
  try {
    const response = await updateAccount(editAccountForm.value)
    showSuccess(response.message)
    editAccountOpen.value = false
    await refreshState(true)
  } catch (error: any) {
    showError(error?.response?.data?.detail || '账号保存失败')
  }
}

function openGroupEditor(mode: 'edit') {
  const target = customGroups.value.find((item) => item.name === contextMenu.value.name)
  if (!target) return
  taxonomyDialog.value = {
    open: true,
    type: 'group',
    mode,
    original_name: target.name,
    form: { name: target.name, color: target.color, priority: target.priority },
  }
  closeContextMenu()
}

function openTagEditor(mode: 'edit') {
  const target = customTags.value.find((item) => item.name === contextMenu.value.name)
  if (!target) return
  taxonomyDialog.value = {
    open: true,
    type: 'tag',
    mode,
    original_name: target.name,
    form: { name: target.name, color: target.color, priority: target.priority },
  }
  closeContextMenu()
}

async function saveTaxonomyDialog() {
  try {
    if (taxonomyDialog.value.type === 'group') {
      const response =
        taxonomyDialog.value.mode === 'create'
          ? await createGroupDetailed(taxonomyDialog.value.form)
          : await updateGroup({
              original_name: taxonomyDialog.value.original_name,
              ...taxonomyDialog.value.form,
            })
      if (dashboard.value) {
        dashboard.value.settings.custom_groups = response.data.custom_groups
      }
      showSuccess(response.message)
    } else {
      const response =
        taxonomyDialog.value.mode === 'create'
          ? await createTag(taxonomyDialog.value.form)
          : await updateTag({
              original_name: taxonomyDialog.value.original_name,
              ...taxonomyDialog.value.form,
            })
      if (dashboard.value) {
        dashboard.value.settings.custom_tags = response.data.custom_tags
      }
      showSuccess(response.message)
    }
    taxonomyDialog.value.open = false
    await refreshState(true)
  } catch (error: any) {
    showError(error?.response?.data?.detail || '保存失败')
  }
}

async function handleDeleteGroup() {
  const name = contextMenu.value.name
  closeContextMenu()
  openConfirmDialog(
    '删除分组',
    `确定删除分组 ${name} 吗？该分组下邮箱会自动归到未分组。`,
    async () => {
      try {
        const response = await deleteGroup(name)
        if (dashboard.value) {
          dashboard.value.settings.custom_groups = response.data.custom_groups
        }
        if (selectedGroupKey.value === name) {
          selectedGroupKey.value = '未分组'
        }
        showSuccess(response.message)
        await refreshState(true)
      } catch (error: any) {
        showError(error?.response?.data?.detail || '删除分组失败')
      }
    },
  )
}

async function handleDeleteTag() {
  const name = contextMenu.value.name
  closeContextMenu()
  openConfirmDialog(
    '删除标签',
    `确定删除标签 ${name} 吗？该标签会从所有邮箱中移除。`,
    async () => {
      try {
        const response = await deleteTag(name)
        if (dashboard.value) {
          dashboard.value.settings.custom_tags = response.data.custom_tags
        }
        if (selectedTagKey.value === name) {
          selectedTagKey.value = ''
        }
        showSuccess(response.message)
        await refreshState(true)
      } catch (error: any) {
        showError(error?.response?.data?.detail || '删除标签失败')
      }
    },
  )
}

async function copyEmail(email: string) {
  closeContextMenu()
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(email)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = email
      textarea.setAttribute('readonly', 'true')
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    showSuccess(`已复制: ${email}`)
  } catch {
    try {
      const textarea = document.createElement('textarea')
      textarea.value = email
      textarea.setAttribute('readonly', 'true')
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      const copied = document.execCommand('copy')
      document.body.removeChild(textarea)
      if (copied) {
        showSuccess(`已复制: ${email}`)
        return
      }
    } catch {
      // Ignore and fall through to toast error.
    }
    showError('复制失败')
  }
}

async function assignGroupFromMenu(groupName: string) {
  const email = contextMenu.value.email
  closeContextMenu()
  try {
    const response = await assignAccountGroup(email, groupName)
    showSuccess(response.message)
    await refreshState(true)
  } catch (error: any) {
    showError(error?.response?.data?.detail || '分组更新失败')
  }
}

async function toggleTagFromMenu(tagName: string) {
  const email = contextMenu.value.email
  const account = allAccounts.value.find((item) => item.email === email)
  if (!account) return
  const tags = account.tags.includes(tagName)
    ? account.tags.filter((item) => item !== tagName)
    : [...account.tags, tagName]
  closeContextMenu()
  try {
    const response = await setAccountTags(email, tags)
    showSuccess(response.message)
    if (editAccountForm.value.original_email === email) {
      editAccountForm.value.tags = response.data.tags
    }
    await refreshState(true)
  } catch (error: any) {
    showError(error?.response?.data?.detail || '标签更新失败')
  }
}

async function runSingleReceive(email: string) {
  closeContextMenu()
  try {
    const response = await receiveAccounts({ emails: [email] })
    showSuccess(response.message)
    await refreshState(true)
  } catch (error: any) {
    showError(error?.response?.data?.detail || '收件失败')
  }
}

async function runSingleRelogin(email: string) {
  closeContextMenu()
  try {
    const response = await reloginAccounts({ emails: [email] })
    showSuccess(response.message)
    await refreshState(true)
  } catch (error: any) {
    showError(error?.response?.data?.detail || '重新登录失败')
  }
}

async function applyFlag(color: string) {
  const email = contextMenu.value.email
  closeContextMenu()
  try {
    const response = await updateFlag(email, color)
    showSuccess(response.message)
    await refreshState(true)
  } catch (error: any) {
    showError(error?.response?.data?.detail || '旗标更新失败')
  }
}
</script>
