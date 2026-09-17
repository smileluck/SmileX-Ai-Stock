/** The global namespace for the app */
declare namespace App {
  /** Theme namespace */
  namespace Theme {
    type ColorPaletteNumber = import('@sa/color').ColorPaletteNumber;

    /** NaiveUI theme overrides that can be specified in preset */
    type NaiveUIThemeOverride = import('naive-ui').GlobalThemeOverrides;

    /** One NaiveUI component's user-configured theme override entry */
    interface ComponentConfigEntry {
      /** Whether this component's override is enabled */
      enabled: boolean;
      /** Values from the structured (form) fields, keyed by GlobalThemeOverrides property name */
      common: Record<string, string | number>;
      /** Parsed object from the advanced JSON5 editor */
      advanced: Record<string, any>;
    }

    /** Map of component name -> config entry, keyed by GlobalThemeOverrides top-level key (e.g. "common", "Button") */
    type ComponentConfigMap = Record<string, ComponentConfigEntry>;

    /** Theme setting */
    interface ThemeSetting {
      /** Theme scheme */
      themeScheme: UnionKey.ThemeScheme;
      /** grayscale mode */
      grayscale: boolean;
      /** colour weakness mode */
      colourWeakness: boolean;
      /** Whether to recommend color */
      recommendColor: boolean;
      /** Theme color */
      themeColor: string;
      /** Theme radius */
      themeRadius: number;
      /** Other color */
      otherColor: OtherColor;
      /** Whether info color is followed by the primary color */
      isInfoFollowPrimary: boolean;
      /** Layout */
      layout: {
        /** Layout mode */
        mode: UnionKey.ThemeLayoutMode;
        /** Scroll mode */
        scrollMode: UnionKey.ThemeScrollMode;
      };
      /** Page */
      page: {
        /** Whether to show the page transition */
        animate: boolean;
        /** Page animate mode */
        animateMode: UnionKey.ThemePageAnimateMode;
      };
      /** Header */
      header: {
        /** Header height */
        height: number;
        /** Header breadcrumb */
        breadcrumb: {
          /** Whether to show the breadcrumb */
          visible: boolean;
          /** Whether to show the breadcrumb icon */
          showIcon: boolean;
        };
        /** Multilingual */
        multilingual: {
          /** Whether to show the multilingual */
          visible: boolean;
        };
        globalSearch: {
          /** Whether to show the GlobalSearch */
          visible: boolean;
        };
      };
      /** Tab */
      tab: {
        /** Whether to show the tab */
        visible: boolean;
        /**
         * Whether to cache the tab
         *
         * If cache, the tabs will get from the local storage when the page is refreshed
         */
        cache: boolean;
        /** Tab height */
        height: number;
        /** Tab mode */
        mode: UnionKey.ThemeTabMode;
        /** Whether to close tab by middle click */
        closeTabByMiddleClick: boolean;
      };
      /** Fixed header and tab */
      fixedHeaderAndTab: boolean;
      /** Sider */
      sider: {
        /** Inverted sider */
        inverted: boolean;
        /** Sider width */
        width: number;
        /** Collapsed sider width */
        collapsedWidth: number;
        /** Sider width when the layout is 'vertical-mix', 'top-hybrid-sidebar-first', or 'top-hybrid-header-first' */
        mixWidth: number;
        /**
         * Collapsed sider width when the layout is 'vertical-mix', 'top-hybrid-sidebar-first', or
         * 'top-hybrid-header-first'
         */
        mixCollapsedWidth: number;
        /** Child menu width when the layout is 'vertical-mix', 'top-hybrid-sidebar-first', or 'top-hybrid-header-first' */
        mixChildMenuWidth: number;
        /** Whether to auto select the first submenu */
        autoSelectFirstMenu: boolean;
      };
      /** Footer */
      footer: {
        /** Whether to show the footer */
        visible: boolean;
        /** Whether fixed the footer */
        fixed: boolean;
        /** Footer height */
        height: number;
        /**
         * Whether float the footer to the right when the layout is 'top-hybrid-sidebar-first' or
         * 'top-hybrid-header-first'
         */
        right: boolean;
      };
      /** Watermark */
      watermark: {
        /** Whether to show the watermark */
        visible: boolean;
        /** Watermark text */
        text: string;
        /** Whether to use user name as watermark text */
        enableUserName: boolean;
        /** Whether to use current time as watermark text */
        enableTime: boolean;
        /** Time format for watermark text */
        timeFormat: string;
      };
      /** define some theme settings tokens, will transform to css variables */
      tokens: {
        light: ThemeSettingToken;
        dark?: {
          [K in keyof ThemeSettingToken]?: Partial<ThemeSettingToken[K]>;
        };
      };
    }

    interface OtherColor {
      info: string;
      success: string;
      warning: string;
      error: string;
    }

    interface ThemeColor extends OtherColor {
      primary: string;
    }

    type ThemeColorKey = keyof ThemeColor;

    type ThemePaletteColor = {
      [key in ThemeColorKey | `${ThemeColorKey}-${ColorPaletteNumber}`]: string;
    };

    type BaseToken = Record<string, Record<string, string>>;

    interface ThemeSettingTokenColor {
      /** the progress bar color, if not set, will use the primary color */
      nprogress?: string;
      container: string;
      layout: string;
      inverted: string;
      'base-text': string;
    }

    interface ThemeSettingTokenBoxShadow {
      header: string;
      sider: string;
      tab: string;
    }

    interface ThemeSettingToken {
      colors: ThemeSettingTokenColor;
      boxShadow: ThemeSettingTokenBoxShadow;
    }

    type ThemeTokenColor = ThemePaletteColor & ThemeSettingTokenColor;

    /** Theme token CSS variables */
    type ThemeTokenCSSVars = {
      colors: ThemeTokenColor & { [key: string]: string };
      boxShadow: ThemeSettingTokenBoxShadow & { [key: string]: string };
    };
  }

  /** Global namespace */
  namespace Global {
    type VNode = import('vue').VNode;
    type RouteLocationNormalizedLoaded = import('vue-router').RouteLocationNormalizedLoaded;
    type RouteKey = import('@elegant-router/types').RouteKey;
    type RouteMap = import('@elegant-router/types').RouteMap;
    type RoutePath = import('@elegant-router/types').RoutePath;
    type LastLevelRouteKey = import('@elegant-router/types').LastLevelRouteKey;

    /** The router push options */
    type RouterPushOptions = {
      query?: Record<string, string>;
      params?: Record<string, string>;
    };

    /** The global header props */
    interface HeaderProps {
      /** Whether to show the logo */
      showLogo?: boolean;
      /** Whether to show the menu toggler */
      showMenuToggler?: boolean;
      /** Whether to show the menu */
      showMenu?: boolean;
    }

    /** The global menu */
    type Menu = {
      /**
       * The menu key
       *
       * Equal to the route key
       */
      key: string;
      /** The menu label */
      label: string;
      /** The menu i18n key */
      i18nKey?: I18n.I18nKey | null;
      /** The route key */
      routeKey: RouteKey;
      /** The route path */
      routePath: RoutePath;
      /** The menu icon */
      icon?: () => VNode;
      /** The menu children */
      children?: Menu[];
    };

    type Breadcrumb = Omit<Menu, 'children'> & {
      options?: Breadcrumb[];
    };

    /** Tab route */
    type TabRoute = Pick<RouteLocationNormalizedLoaded, 'name' | 'path' | 'meta'> &
      Partial<Pick<RouteLocationNormalizedLoaded, 'fullPath' | 'query' | 'matched'>>;

    /** The global tab */
    type Tab = {
      /** The tab id */
      id: string;
      /** The tab label */
      label: string;
      /**
       * The new tab label
       *
       * If set, the tab label will be replaced by this value
       */
      newLabel?: string;
      /**
       * The old tab label
       *
       * when reset the tab label, the tab label will be replaced by this value
       */
      oldLabel?: string;
      /** The tab route key */
      routeKey: LastLevelRouteKey;
      /** The tab route path */
      routePath: RouteMap[LastLevelRouteKey];
      /** The tab route full path */
      fullPath: string;
      /** The tab fixed index */
      fixedIndex?: number | null;
      /**
       * Tab icon
       *
       * Iconify icon
       */
      icon?: string;
      /**
       * Tab local icon
       *
       * Local icon
       */
      localIcon?: string;
      /** I18n key */
      i18nKey?: I18n.I18nKey | null;
    };

    /** Form rule */
    type FormRule = import('naive-ui').FormItemRule;

    /** The global dropdown key */
    type DropdownKey = 'closeCurrent' | 'closeOther' | 'closeLeft' | 'closeRight' | 'closeAll' | 'pin' | 'unpin';
  }

  /**
   * I18n namespace
   *
   * Locales type
   */
  namespace I18n {
    type RouteKey = import('@elegant-router/types').RouteKey;

    type LangType = 'en-US' | 'zh-CN';

    type LangOption = {
      label: string;
      key: LangType;
    };

    type I18nRouteKey = Exclude<RouteKey, 'root' | 'not-found'>;

    type FormMsg = {
      required: string;
      invalid: string;
    };

    type Schema = {
      system: {
        title: string;
        updateTitle: string;
        updateContent: string;
        updateConfirm: string;
        updateCancel: string;
      };
      common: {
        selectAtLeastOne: string;
        pleaseSelect: string;
        action: string;
        add: string;
        addSuccess: string;
        backToHome: string;
        back: string;
        batchDelete: string;
        cancel: string;
        close: string;
        check: string;
        selectAll: string;
        expandColumn: string;
        columnSetting: string;
        config: string;
        confirm: string;
        delete: string;
        deleteSuccess: string;
        deleteFailed: string;
        confirmDelete: string;
        edit: string;
        warning: string;
        error: string;
        index: string;
        keywordSearch: string;
        logout: string;
        logoutConfirm: string;
        lookForward: string;
        modify: string;
        modifySuccess: string;
        saveSuccess: string;
        noData: string;
        operate: string;
        pleaseCheckValue: string;
        pleaseEnter: string;
        status: string;
        title: string;
        refresh: string;
        reset: string;
        search: string;
        switch: string;
        tip: string;
        trigger: string;
        update: string;
        updateSuccess: string;
        updateFailed: string;
        userCenter: string;
        changePassword: string;
        loadDataFailed: string;
        yesOrNo: {
          yes: string;
          no: string;
        };
        actions: {
          list: string;
          add: string;
          edit: string;
          delete: string;
          remove: string;
          publish: string;
          detail: string;
          status: string;
          trigger: string;
          view: string;
          kick: string;
          download: string;
          upload: string;
          assign: string;
          logDetail: string;
          logDelete: string;
        };
      };
      request: {
        logout: string;
        logoutMsg: string;
        logoutWithModal: string;
        logoutWithModalMsg: string;
        refreshToken: string;
        tokenExpired: string;
        error: string;
      };
      captcha: {
        success: string;
        fail: string;
        refresh: string;
        slideToVerify: string;
        completeFirst: string;
        selectPlaceholder: string;
      };
      theme: {
        themeDrawerTitle: string;
        tabs: {
          appearance: string;
          layout: string;
          general: string;
          preset: string;
          component: string;
        };
        appearance: {
          themeSchema: { title: string } & Record<UnionKey.ThemeScheme, string>;
          grayscale: string;
          colourWeakness: string;
          themeColor: {
            title: string;
            followPrimary: string;
          } & Record<Theme.ThemeColorKey, string>;
          recommendColor: string;
          recommendColorDesc: string;
          themeRadius: {
            title: string;
          };
          preset: {
            title: string;
            apply: string;
            applySuccess: string;
            [key: string]:
              | {
                  name: string;
                  desc: string;
                }
              | string;
          };
        };
        layout: {
          layoutMode: { title: string } & Record<UnionKey.ThemeLayoutMode, string> & {
              [K in `${UnionKey.ThemeLayoutMode}_detail`]: string;
            };
          tab: {
            title: string;
            visible: string;
            cache: string;
            cacheTip: string;
            height: string;
            mode: { title: string } & Record<UnionKey.ThemeTabMode, string>;
            closeByMiddleClick: string;
            closeByMiddleClickTip: string;
          };
          header: {
            title: string;
            height: string;
            breadcrumb: {
              visible: string;
              showIcon: string;
            };
          };
          sider: {
            title: string;
            inverted: string;
            width: string;
            collapsedWidth: string;
            mixWidth: string;
            mixCollapsedWidth: string;
            mixChildMenuWidth: string;
            autoSelectFirstMenu: string;
            autoSelectFirstMenuTip: string;
          };
          footer: {
            title: string;
            visible: string;
            fixed: string;
            height: string;
            right: string;
          };
          content: {
            title: string;
            scrollMode: { title: string; tip: string } & Record<UnionKey.ThemeScrollMode, string>;
            page: {
              animate: string;
              mode: { title: string } & Record<UnionKey.ThemePageAnimateMode, string>;
            };
            fixedHeaderAndTab: string;
          };
        };
        general: {
          title: string;
          watermark: {
            title: string;
            visible: string;
            text: string;
            enableUserName: string;
            enableTime: string;
            timeFormat: string;
          };
          multilingual: {
            title: string;
            visible: string;
          };
          globalSearch: {
            title: string;
            visible: string;
          };
        };
        configOperation: {
          copyConfig: string;
          copySuccessMsg: string;
          resetConfig: string;
          resetSuccessMsg: string;
        };
        componentConfig: {
          title: string;
          searchPlaceholder: string;
          noMatch: string;
          searchPropPlaceholder: string;
          enable: string;
          enabled: string;
          notEnabledHint: string;
          noProps: string;
          groupColor: string;
          groupSize: string;
          groupFont: string;
          groupOther: string;
          advanced: string;
          advancedHint: string;
          jsonValid: string;
          jsonInvalid: string;
          copy: string;
          copySuccess: string;
          preview: string;
          components: Record<string, string>;
        };
      };
      route: Record<I18nRouteKey, string>;
      page: {
        login: {
          common: {
            loginOrRegister: string;
            userNamePlaceholder: string;
            phonePlaceholder: string;
            codePlaceholder: string;
            passwordPlaceholder: string;
            confirmPasswordPlaceholder: string;
            codeLogin: string;
            confirm: string;
            back: string;
            validateSuccess: string;
            loginSuccess: string;
            welcomeBack: string;
          };
          pwdLogin: {
            title: string;
            rememberMe: string;
            forgetPassword: string;
            register: string;
            otherAccountLogin: string;
            otherLoginMode: string;
            superAdmin: string;
            admin: string;
            user: string;
          };
          codeLogin: {
            title: string;
            getCode: string;
            reGetCode: string;
            sendCodeSuccess: string;
            imageCodePlaceholder: string;
          };
          register: {
            title: string;
            agreement: string;
            protocol: string;
            policy: string;
          };
          resetPwd: {
            title: string;
          };
          bindWeChat: {
            title: string;
          };
        };
        home: {
          welcome: string;
          userCount: string;
          roleCount: string;
          onlineCount: string;
          todayLoginCount: string;
          recentLogin: string;
          latestNotice: string;
          loginSuccess: string;
          loginFailed: string;
          noData: string;
        };
        monitor: {
          systemResources: string;
          apiStats: string;
          systemInfo: string;
          osName: string;
          cpuCount: string;
          cpuUsage: string;
          memoryUsage: string;
          diskUsage: string;
          avgResponseTime: string;
          errorRate: string;
          uptime: string;
          processCount: string;
          pythonVersion: string;
          day: string;
          hour: string;
          minute: string;
        };
        about: {
          title: string;
          subtitle: string;
          intro: string;
          techStackTitle: string;
          featuresTitle: string;
          feat1: string;
          feat2: string;
          feat3: string;
          feat4: string;
          feat5: string;
          feat6: string;
          gitHistory: string;
          gitUnavailable: string;
          commitsCount: string;
        };

        demo: {
          openapiTest: {
            title: string;
            tip: string;
            appId: string;
            appSecret: string;
            method: string;
            path: string;
            body: string;
            url: string;
            send: string;
            needCredential: string;
            signatureTitle: string;
            timestamp: string;
            nonce: string;
            signature: string;
            canonical: string;
            responseTitle: string;
            status: string;
            requestId: string;
          };
          stockSdk: {
            title: string;
            tip: string;
            akshareTitle: string;
            symbol: string;
            symbolPlaceholder: string;
            baostockTitle: string;
            code: string;
            codePlaceholder: string;
            days: string;
            query: string;
            empty: string;
            resultCount: string;
            item: string;
            value: string;
            date: string;
            open: string;
            high: string;
            low: string;
            close: string;
            volume: string;
            amount: string;
            pctChg: string;
          };
          upload: {
            title: string;
            singleUpload: string;
            multiUpload: string;
            selectFile: string;
            selectFiles: string;
            uploading: string;
            uploadSuccess: string;
            uploadFailed: string;
            fileSize: string;
            fileType: string;
            fileName: string;
            uploadResult: string;
            dragOrClick: string;
            startUpload: string;
          };
          dict: {
            selectDemo: string;
            selectLabel: string;
            selectWithDefault: string;
            tagDemo: string;
            tagLabel: string;
            textDemo: string;
            textLabel: string;
            tableDemo: string;
            tableLabel: string;
          };
        };

        manage: {
          common: {
            status: {
              enable: string;
              disable: string;
            };
          };
          role: {
            title: string;
            roleName: string;
            roleCode: string;
            roleStatus: string;
            roleDesc: string;
            dataScope: string;
            dataScopes: {
              ALL: string;
              DEPT_AND_SUB: string;
              DEPT_ONLY: string;
              SELF: string;
            };
            form: {
              roleName: string;
              roleCode: string;
              roleStatus: string;
              roleDesc: string;
              nameMaxLength: string;
              descMaxLength: string;
            };
            addRole: string;
            editRole: string;
            menuAuth: string;
            buttonAuth: string;
          };
          user: {
            title: string;
            userName: string;
            userGender: string;
            password: string;
            confirmPassword: string;
            nickName: string;
            userPhone: string;
            userEmail: string;
            userStatus: string;
            userRole: string;
            isSuperuser: string;
            changePassword: string;
            lastLoginTime: string;
            lastLoginIp: string;
            form: {
              userName: string;
              userGender: string;
              nickName: string;
              userPhone: string;
              userEmail: string;
              userStatus: string;
              userRole: string;
              isSuperuser: string;
              newPassword: string;
              confirmPassword: string;
              passwordMinLength: string;
              passwordNotMatch: string;
              usernameLength: string;
              passwordLength: string;
              emailFormat: string;
              phoneFormat: string;
            };
            addUser: string;
            editUser: string;
            dept: string;
            gender: {
              male: string;
              female: string;
            };
          };
          appUser: {
            title: string;
            userName: string;
            phoneCode: string;
            userPhone: string;
            userEmail: string;
            userStatus: string;
            password: string;
            confirmPassword: string;
            changePassword: string;
            bindWechat: string;
            bound: string;
            unbound: string;
            lastLoginTime: string;
            lastLoginIp: string;
            addUser: string;
            editUser: string;
            form: {
              userName: string;
              phoneCode: string;
              userPhone: string;
              userEmail: string;
              userStatus: string;
              newPassword: string;
              confirmPassword: string;
              passwordPlaceholder: string;
              passwordNotMatch: string;
              emailFormat: string;
              phoneFormat: string;
            };
          };
          menu: {
            home: string;
            title: string;
            id: string;
            parentId: string;
            parentMenu: string;
            menuType: string;
            menuName: string;
            routeName: string;
            routePath: string;
            pathParam: string;
            layout: string;
            layoutBase: string;
            layoutBlank: string;
            page: string;
            i18nKey: string;
            icon: string;
            localIcon: string;
            iconTypeTitle: string;
            order: string;
            constant: string;
            keepAlive: string;
            href: string;
            hideInMenu: string;
            activeMenu: string;
            multiTab: string;
            fixedIndexInTab: string;
            query: string;
            button: string;
            buttonCode: string;
            buttonDesc: string;
            permission: string;
            isSystem: string;
            menuStatus: string;
            form: {
              home: string;
              parentMenu: string;
              menuType: string;
              menuName: string;
              routeName: string;
              routePath: string;
              pathParam: string;
              layout: string;
              page: string;
              i18nKey: string;
              icon: string;
              localIcon: string;
              order: string;
              keepAlive: string;
              href: string;
              hideInMenu: string;
              activeMenu: string;
              multiTab: string;
              fixedInTab: string;
              fixedIndexInTab: string;
              queryKey: string;
              queryValue: string;
              button: string;
              buttonCode: string;
              buttonDesc: string;
              permission: string;
              isSystem: string;
              menuStatus: string;
            };
            addMenu: string;
            editMenu: string;
            addChildMenu: string;
            addChildButton: string;
            type: {
              directory: string;
              menu: string;
              button: string;
            };
            iconType: {
              iconify: string;
              local: string;
            };
          };
          dict: {
            title: string;
            dictManage: string;
            itemManage: string;
            itemTitle: string;
            dictName: string;
            dictCode: string;
            dictDesc: string;
            dictStatus: string;
            isSystem: string;
            sort: string;
            itemValue: string;
            itemLabel: string;
            itemDesc: string;
            itemStatus: string;
            form: {
              dictName: string;
              dictCode: string;
              dictDesc: string;
              dictStatus: string;
              isSystem: string;
              sort: string;
              itemValue: string;
              itemLabel: string;
              itemDesc: string;
              extInfo: string;
              itemStatus: string;
            };
            addDict: string;
            editDict: string;
            addDictItem: string;
            editDictItem: string;
           pleaseSelectDict: string;
         };
          aiModel: {
            title: string;
            modelName: string;
            provider: string;
            modelId: string;
            baseUrl: string;
            apiKey: string;
            temperature: string;
            maxTokens: string;
            isDefault: string;
            status: string;
            remark: string;
            addModel: string;
            editModel: string;
            modelManage: string;
            bindingManage: string;
            bindingTitle: string;
            function: string;
            boundModel: string;
            bindingStatus: string;
            bindingTip: string;
            useDefault: string;
            selectModel: string;
            selectModelFirst: string;
            testConnection: string;
            testFailed: string;
            billingMode: string;
            payAsYouGo: string;
            codingPlan: string;
            fetchModels: string;
            form: {
              modelName: string;
              provider: string;
              billingMode: string;
              modelId: string;
              baseUrl: string;
              apiKey: string;
              apiKeyEditHint: string;
              apiKeyRequired: string;
              modelsFetched: string;
              modelsFetchedHint: string;
              noModels: string;
              remark: string;
              status: string;
              isDefault: string;
            };
          };
         config: {
           title: string;
           configKey: string;
           configValue: string;
            defaultValue: string;
            configDesc: string;
            configType: string;
            configGroup: string;
            editable: string;
            isSystem: string;
            required: string;
            resetConfig: string;
            validationRule: string;
            beautifyJson: string;
            editInModal: string;
            editJson: string;
            form: {
              configKey: string;
              configValue: string;
              defaultValue: string;
              validationRule: string;
              configDesc: string;
              configType: string;
              configGroup: string;
              editable: string;
              isSystem: string;
              required: string;
              invalidNumber: string;
              invalidBoolean: string;
              invalidJson: string;
              invalidArray: string;
              jsonEmpty: string;
              jsonBeautifySuccess: string;
              jsonFormatError: string;
            };
            addConfig: string;
            editConfig: string;
            type: {
              string: string;
              number: string;
              boolean: string;
              json: string;
              array: string;
            };
            group: {
              system: string;
              security: string;
              log: string;
              network: string;
              storage: string;
              custom: string;
            };
          };
          ipBlacklist: {
            title: string;
            ip: string;
            type: string;
            typePermanent: string;
            typeTemporary: string;
            reason: string;
            expireAt: string;
            expireAtPlaceholder: string;
            expireRequired: string;
            createdAt: string;
            reasonPlaceholder: string;
            addTitle: string;
            form: {
              ip: string;
              type: string;
            };
          };
          announcement: {
            title: string;
            noticeType: string;
            noticeContent: string;
            targetTypeLabel: string;
            targetRole: string;
            targetUser: string;
            priority: string;
            senderName: string;
            publishedAt: string;
            publish: string;
            publishSuccess: string;
            addAnnouncement: string;
            editAnnouncement: string;
            deleteAnnouncement: string;
            status: {
              published: string;
              draft: string;
            };
            type: {
              announcement: string;
              system: string;
              operation: string;
              approval: string;
            };
            targetType: {
              all: string;
              role: string;
              user: string;
            };
            priorities: {
              low: string;
              normal: string;
              high: string;
              urgent: string;
            };
            form: {
              title: string;
              content: string;
              type: string;
              targetType: string;
              status: string;
              priority: string;
              roleIds: string;
              userIds: string;
              roleIdsPlaceholder: string;
              userIdsPlaceholder: string;
            };
          };
          file: {
            title: string;
            fileName: string;
            fileSize: string;
            fileType: string;
            fileExtension: string;
            storagePlatform: string;
            uploadTime: string;
            upload: string;
            download: string;
            preview: string;
            previewTitle: string;
            previewNotSupported: string;
            videoNotSupported: string;
            platform: {
              local: string;
              oss: string;
            };
            form: {
              fileName: string;
              fileExtension: string;
              storagePlatform: string;
            };
          };
          dept: {
            title: string;
            deptName: string;
            deptCode: string;
            parentDept: string;
            sort: string;
            status: string;
            addDept: string;
            editDept: string;
            addChild: string;
            form: {
              parentDept: string;
              deptName: string;
              deptCode: string;
            };
          };
          merchant: {
            title: string;
            merchantName: string;
            merchantCode: string;
            appId: string;
            appSecret: string;
            contactName: string;
            contactPhone: string;
            contactEmail: string;
            remark: string;
            sort: string;
            status: string;
            secretUpdatedAt: string;
            addMerchant: string;
            editMerchant: string;
            resetSecret: string;
            resetSecretConfirm: string;
            secretResultTitle: string;
            secretOnceWarning: string;
            copy: string;
            copied: string;
            copyFailed: string;
            form: {
              merchantName: string;
              merchantCode: string;
              appId: string;
              contactName: string;
              contactPhone: string;
              contactEmail: string;
              remark: string;
              status: string;
              emailFormat: string;
              phoneFormat: string;
            };
          };
          openapiLog: {
            title: string;
            appId: string;
            merchantName: string;
            method: string;
            path: string;
            status: string;
            errCode: string;
            clientIp: string;
            latency: string;
            createdAt: string;
            form: {
              appId: string;
              path: string;
              method: string;
              errCode: string;
              clientIp: string;
              status: string;
            };
          };
          scheduler: {
            title: string;
            taskName: string;
            taskKey: string;
            description: string;
            cronExpression: string;
            triggerType: string;
            triggerTypes: {
              cron: string;
              interval: string;
              date: string;
            };
            status: string;
            statusEnabled: string;
            statusDisabled: string;
            enable: string;
            disable: string;
            lastRunAt: string;
            nextRunAt: string;
            lastStatus: string;
            lastStatuses: {
              success: string;
              failed: string;
              running: string;
              timeout: string;
            };
            timeout: string;
            maxRetries: string;
            concurrentPolicy: string;
            concurrentPolicies: {
              skip: string;
              replace: string;
              run: string;
            };
            manualTrigger: string;
            manualTriggerConfirm: string;
            manualTriggerSuccess: string;
            cronPreview: string;
            nextRunTimes: string;
            syncRegistry: string;
            syncRegistrySuccess: string;
            viewLogs: string;
            triggerParams: string;
            addTask: string;
            editTask: string;
            isSystem: string;
            taskCategory: string;
            taskCategories: {
              generic: string;
              system: string;
              specialist: string;
            };
            template: string;
            templatePlaceholder: string;
            taskKeyPlaceholder: string;
            taskKeyHint: string;
            taskKeyRequired: string;
            advancedConfig: string;
            schemaLoading: string;
            noParams: string;
            paramPlaceholder: string;
            form: {
              taskName: string;
              taskKey: string;
              cronExpression: string;
              triggerType: string;
              status: string;
              concurrentPolicy: string;
              description: string;
            };
          };
          schedulerLog: {
            title: string;
            taskName: string;
            status: string;
            startTime: string;
            endTime: string;
            duration: string;
            triggeredBy: string;
            triggeredByValues: {
              scheduler: string;
              manual: string;
            };
            result: string;
            errorMessage: string;
            viewDetail: string;
            clear: string;
            clearConfirm: string;
            detailTitle: string;
            form: {
              taskName: string;
              status: string;
              timeRange: string;
            };
          };
        };
        log: {
          loginLog: {
            title: string;
            username: string;
            ip: string;
            status: string;
            detail: string;
            userAgent: string;
            loginTime: string;
            success: string;
            failed: string;
            clear: string;
            clearConfirm: string;
            form: {
              username: string;
              ip: string;
              status: string;
              timeRange: string;
              startTime: string;
              endTime: string;
            };
          };
          operationLog: {
            title: string;
            username: string;
            module: string;
            action: string;
            description: string;
            method: string;
            path: string;
            ip: string;
            responseCode: string;
            responseResult: string;
            elapsedMs: string;
            requestParams: string;
            operateTime: string;
            viewDetail: string;
            detailTitle: string;
            clear: string;
            clearConfirm: string;
            form: {
              username: string;
              module: string;
              action: string;
              timeRange: string;
              startTime: string;
              endTime: string;
            };
          };
          onlineUser: {
            title: string;
            username: string;
            nickname: string;
            ip: string;
            userAgent: string;
            loginTime: string;
            kick: string;
            kickAll: string;
            kickConfirm: string;
            kickAllConfirm: string;
            kickSuccess: string;
            kickAllSuccess: string;
            form: {
              username: string;
              ip: string;
            };
          };
        };
        news: {
          title: string;
          source: string;
          summary: string;
          publishedAt: string;
          dateRange: string;
          allSources: string;
          viewOriginal: string;
        form: {
          keyword: string;
           source: string;
        };
        };
        aStock: {
          marketOverview: {
            title: string;
            todayMarket: string;
            historyMarket: string;
            totalTurnover: string;
            indexCount: string;
            turnover: string;
            volume: string;
            amplitude: string;
            highLow: string;
            high: string;
            low: string;
            open: string;
            prevClose: string;
            closePrice: string;
            changePct: string;
            miniTrend: string;
            trend: string;
            netInflow: string;
            lastRefresh: string;
            sync: string;
            syncSuccess: string;
            datePlaceholder: string;
            noData: string;
          };
          industryBoard: {
            title: string;
            industry: string;
            concept: string;
            boardName: string;
            changePct: string;
            turnover: string;
            turnoverRate: string;
            netInflow: string;
            breadth: string;
            leadingStock: string;
            sortByChangePct: string;
            sortByNetInflow: string;
            desc: string;
            asc: string;
            sync: string;
            syncSuccess: string;
            datePlaceholder: string;
            lastRefresh: string;
          };
          limitUp: {
            title: string;
            totalCount: string;
            brokenCount: string;
            poolStatus: string;
            statusSealed: string;
            statusBroken: string;
            poolAll: string;
            poolLimitUp: string;
            poolBroken: string;
            mainCount: string;
            chinextCount: string;
            starCount: string;
            bseCount: string;
            maxConsecutive: string;
            stockCode: string;
            stockName: string;
            marketBoard: string;
            latestPrice: string;
            changePct: string;
            turnoverRate: string;
            turnover: string;
            amplitude: string;
            firstSeal: string;
            lastSeal: string;
            consecutive: string;
            continuationProb: string;
            probHigh: string;
            probMid: string;
            probLow: string;
            probFactors: string;
            factorConsecutive: string;
            factorSealRatio: string;
            factorBreakCountZero: string;
            factorBreakCount: string;
            factorFirstSeal: string;
            factorTurnoverRate: string;
            industry: string;
            reason: string;
            all: string;
            main: string;
            chinext: string;
            star: string;
            lastRefresh: string;
            sync: string;
            syncSuccess: string;
            datePlaceholder: string;
          };
          stockHot: {
            title: string;
            rank: string;
            stockName: string;
            stockCode: string;
            latestPrice: string;
            changePct: string;
            hotValue: string;
            dateLabel: string;
            datePlaceholder: string;
            lastRefresh: string;
            sync: string;
          };
          blockTrade: {
            title: string;
            tabDaily: string;
            tabActive: string;
            rank: string;
            stockName: string;
            latestPrice: string;
            closePrice: string;
            tradePrice: string;
            premiumRate: string;
            changePct: string;
            tradeCount: string;
            tradeAmount: string;
            amountRatio: string;
            listCountTotal: string;
            listCountPremium: string;
            listCountDiscount: string;
            totalAmount: string;
            lastListDate: string;
            avgChange1d: string;
            avgChange5d: string;
            avgChange20d: string;
            window1m: string;
            window3m: string;
            window6m: string;
            window1y: string;
            dateLabel: string;
            datePlaceholder: string;
            lastRefresh: string;
            sync: string;
            syncSuccess: string;
            noData: string;
          };
        };
        research: {
          title: string;
          subtitle: string;
          syncBtn: string;
          syncDone: string;
          statTotal: string;
          statTotalSuffix: string;
          statStocks: string;
          statOrgs: string;
          hotStocks: string;
          hotOrgs: string;
          listTitle: string;
          stockCol: string;
          titleCol: string;
          orgCol: string;
          ratingCol: string;
          industryCol: string;
          forecastCol: string;
          dateCol: string;
          stockPlaceholder: string;
          keywordPlaceholder: string;
          orgPlaceholder: string;
          ratingPlaceholder: string;
          datePlaceholder: string;
          searchBtn: string;
          statTitle: string;
          tabStats: string;
          tabList: string;
          statSubtitle: string;
          range7d: string;
          range1m: string;
          range3m: string;
          range6m: string;
          range1y: string;
          statReportCount: string;
          statPositiveCount: string;
          statOrgCount: string;
          statLatestDate: string;
          viewReports: string;
        };
        financial: {
          title: string;
          subtitle: string;
          codePlaceholder: string;
          codeInvalid: string;
          queryBtn: string;
          interpretBtn: string;
          interpretSubmitted: string;
          reportTitle: string;
          metricsTitle: string;
          historyTitle: string;
          stockCol: string;
          periodCol: string;
          industryCol: string;
          ratingLabel: string;
          nextRatingLabel: string;
          forecastLabel: string;
          forecastDriversLabel: string;
          researchBriefLabel: string;
          strategyBtn: string;
          strategyTitle: string;
          strategyTip: string;
          strategyPlaceholder: string;
          strategySaved: string;
          highlightsLabel: string;
          risksLabel: string;
          emptyTip: string;
          drawerLoading: string;
        };
      aiStrategy: {
        tabStrategies: string;
        tabPositions: string;
        tabStats: string;
        tabTemplates: string;
        templateTag: string;
        templateTip: string;
        clone: string;
        cloneThis: string;
        cloneConfirm: string;
        cloneSuccess: string;
        export: string;
        exportSuccess: string;
        publish: string;
        unpublish: string;
        publishTitle: string;
        publishTags: string;
        publishTip: string;
        publishSuccess: string;
        unpublishSuccess: string;
        importStrategy: string;
        importTitle: string;
        importPlaceholder: string;
        importTip: string;
        importInputRequired: string;
        importInvalidJson: string;
        importSuccess: string;
        tagsCol: string;
        cloneCountCol: string;
        lastBacktestCol: string;
        noBacktest: string;
        btTrades: string;
        createStrategy: string;
        editStrategy: string;
        periodPreMarket: string;
        periodMorning: string;
        periodNoon: string;
        periodTail: string;
        periodPostClose: string;
        periodManual: string;
        lastExecuted: string;
        run: string;
        runHistory: string;
        runHistoryOf: string;
        deleteConfirm: string;
        runSubmitted: string;
        stock: string;
        strategyCol: string;
        buyPrice: string;
        buyTime: string;
        targetSell: string;
        stopLossPrice: string;
        latestPrice: string;
        floatingPnl: string;
        positionStatus: string;
        statusHolding: string;
        statusClosed: string;
        statusAll: string;
        enabled: string;
        disabled: string;
        returnRate: string;
        sellPrice: string;
        sellTime: string;
        close: string;
        closeConfirm: string;
        closeSuccess: string;
        trackNow: string;
        trackDone: string;
        lastTrack: string;
        searchName: string;
        searchCategory: string;
        categoryAuction: string;
        categoryNoon: string;
        categoryTail: string;
        categoryBlueChip: string;
        categoryGeneral: string;
        presetTag: string;
        typePrompt: string;
        typeRule: string;
        ruleTag: string;
        searchCode: string;
        filterStrategy: string;
        filterTimeRange: string;
        holdingCount: string;
        closedCount: string;
        closedCount2: string;
        winCount: string;
        lossCount: string;
        winRate: string;
        totalReturn: string;
        avgReturn: string;
        bestReturn: string;
        worstReturn: string;
        compoundReturn: string;
        compoundTip: string;
        equityCurve: string;
        statsSelectStrategy: string;
        bySellReason: string;
        byRunPeriod: string;
        attrName: string;
        attrCount: string;
        attrTotalReturn: string;
        holdingCountCol: string;
        periodReview: string;
        periodUnknown: string;
        openedCount: string;
        execTime: string;
        execPeriod: string;
        execStatus: string;
        execOk: string;
        execFail: string;
        execRunning: string;
        signalsCol: string;
        reasonStopLoss: string;
        reasonTakeProfit: string;
        reasonTarget: string;
        reasonTrailingStop: string;
        reasonAi: string;
        reasonManual: string;
        form: {
          name: string;
          namePlaceholder: string;
          nameRequired: string;
          description: string;
          category: string;
          prompt: string;
          promptPlaceholder: string;
          stockPool: string;
          stockPoolPlaceholder: string;
          stockPoolPlaceholderRule: string;
          strategyType: string;
          strategyTypeTip: string;
          buyConditions: string;
          buyConditionRequired: string;
          sellConditions: string;
          sellConditionsTip: string;
          rulePoolRequired: string;
          periods: string;
          periodRequired: string;
          maxPositions: string;
          stopLoss: string;
          takeProfit: string;
          status: string;
          tip: string;
        };
      };
      aiBacktest: {
        formTitle: string;
        modeTip: string;
        tagAi: string;
        tagRule: string;
        formStrategy: string;
        formStrategyPlaceholder: string;
        formRange: string;
        formCapital: string;
        advanced: string;
        slippage: string;
        slippageModel: string;
        slippageFixed: string;
        slippageAmp: string;
        slippageAmpLabel: string;
        slippageAmpTip: string;
        sweep: {
          entry: string;
          title: string;
          gridTip: string;
          stopLoss: string;
          takeProfit: string;
          trailing: string;
          scanTip: string;
          scanCondition: string;
          scanValues: string;
          comboCount: string;
          comboOver: string;
          comboEmpty: string;
          submit: string;
          resultTitle: string;
          colParams: string;
          best: string;
          baseline: string;
          apply: string;
          applyConfirm: string;
          applySuccess: string;
        };
        commission: string;
        stampTax: string;
        submit: string;
        submitSuccess: string;
        strategyRequired: string;
        rangeRequired: string;
        listTitle: string;
        filterStrategy: string;
        strategyCol: string;
        rangeCol: string;
        statusCol: string;
        statusRunning: string;
        statusSuccess: string;
        statusFailed: string;
        totalReturn: string;
        annualReturn: string;
        maxDrawdown: string;
        sharpe: string;
        winRate: string;
        profitFactor: string;
        tradeCount: string;
        finalEquity: string;
        createdAt: string;
        lastRefresh: string;
        detail: string;
        detailTitle: string;
        deleteConfirm: string;
        equity: string;
        equityCurve: string;
        warnings: string;
        tradesTitle: string;
        action: string;
        actionBuy: string;
        actionSell: string;
        stock: string;
        tradeDate: string;
        price: string;
        quantity: string;
        amount: string;
        fee: string;
        returnRate: string;
        reason: string;
        reasonStopLoss: string;
        reasonTarget: string;
        reasonTrailingStop: string;
        reasonAi: string;
        reasonBacktestEnd: string;
      };
      aiFactor: {
        tabLibrary: string;
        tabCalc: string;
        tabScreen: string;
        libraryTitle: string;
        create: string;
        import: string;
        filterCategory: string;
        filterSource: string;
        keywordPlaceholder: string;
        nameCol: string;
        codeCol: string;
        categoryCol: string;
        sourceCol: string;
        formulaCol: string;
        statusCol: string;
        enabled: string;
        disabled: string;
        sourcePreset: string;
        sourceImported: string;
        sourceCustom: string;
        categoryPrice: string;
        categoryMomentum: string;
        categoryVolume: string;
        categoryVolatility: string;
        categoryImported: string;
        categoryCustom: string;
        deleteConfirm: string;
        presetTag: string;
        presetDeleteTip: string;
        createTitle: string;
        editTitle: string;
        form: {
          name: string;
          namePlaceholder: string;
          nameRequired: string;
          code: string;
          codePlaceholder: string;
          codeRequired: string;
          codeImmutable: string;
          category: string;
          formula: string;
          formulaTip: string;
          formulaRequired: string;
          description: string;
          sourceUrl: string;
          status: string;
        };
        importModal: {
          title: string;
          byUrl: string;
          byContent: string;
          formatTip: string;
          inputRequired: string;
          submit: string;
          resultTitle: string;
          importedCount: string;
          skippedCount: string;
        };
        calc: {
          formTitle: string;
          factor: string;
          factorPlaceholder: string;
          codes: string;
          codesPlaceholder: string;
          fromStrategy: string;
          fromStrategyPlaceholder: string;
          poolEmpty: string;
          date: string;
          datePlaceholder: string;
          lookback: string;
          run: string;
          factorRequired: string;
          codesRequired: string;
          resultTitle: string;
          stockCol: string;
          valueCol: string;
        };
        screen: {
          formTitle: string;
          poolSource: string;
          poolManual: string;
          poolStrategy: string;
          codesPlaceholder: string;
          strategyPlaceholder: string;
          conditions: string;
          conditionsTip: string;
          factorPlaceholder: string;
          opTopN: string;
          valuePlaceholder: string;
          addCondition: string;
          run: string;
          conditionRequired: string;
          poolRequired: string;
          strategyRequired: string;
          resultTitle: string;
          matchedCount: string;
          stockCodeCol: string;
          stockNameCol: string;
          savePool: string;
          savePoolTitle: string;
          targetStrategy: string;
          targetStrategyRequired: string;
          savePoolTip: string;
          saveSuccess: string;
        };
      };
      aiAnalysis: {
        reportTitle: string;
        generate: string;
        runSubmitted: string;
        statusRunning: string;
        statusSuccess: string;
        statusFailed: string;
        generatingTip: string;
        failedTip: string;
        emptyTip: string;
        historyBtn: string;
        historyTitle: string;
        backToLatest: string;
        viewBtn: string;
        execTime: string;
        triggerCol: string;
        statusCol: string;
        summaryCol: string;
        triggerSchedule: string;
        triggerManual: string;
        sentimentLabel: string;
        scoreLabel: string;
        summaryLabel: string;
        rotationLabel: string;
        hotBoardsLabel: string;
        keyPointsLabel: string;
        tomorrowLabel: string;
        todayOutlookLabel: string;
        sessionClose: string;
        sessionMorning: string;
        sessionWeekly: string;
        macroNewsLabel: string;
        stockNewsLabel: string;
        newsSectionEmpty: string;
        morningStrategyTitle: string;
        strategyBtn: string;
        strategyTitle: string;
        strategyPromptLabel: string;
        strategyPromptPlaceholder: string;
        morningPromptPlaceholder: string;
        includeTomorrow: string;
        includeTomorrowTip: string;
        includeTodayOutlook: string;
        includeTodayTip: string;
        todayPromptLabel: string;
        todayPromptPlaceholder: string;
        newsInjectTip: string;
        strategyEffectTip: string;
        tomorrowPromptLabel: string;
        tomorrowPromptPlaceholder: string;
        saveBtn: string;
        strategySaved: string;
        market: {
          indicesTitle: string;
          totalTurnover: string;
          mainInflowLabel: string;
          turnover: string;
          compareLabel: string;
          volumeUp: string;
          volumeDown: string;
        };
        sector: {
          boardTitle: string;
          topNTip: string;
          industryTab: string;
          conceptTab: string;
          rankCol: string;
          boardCol: string;
          changePctCol: string;
          turnoverCol: string;
          netInflowCol: string;
          risingFallingCol: string;
          leadingStockCol: string;
        };
        rotation: {
          boardTitle: string;
          historyDaysTip: string;
          syncStocksBtn: string;
          backfillBtn: string;
          syncSuccessTip: string;
          backfillTip: string;
          tabOverview: string;
          tabTomorrow: string;
          tabSwitch: string;
          rankCol: string;
          boardCol: string;
          changePctCol: string;
          gain3dCol: string;
          gain5dCol: string;
          gain10dCol: string;
          rankChangeCol: string;
          volumeRatioCol: string;
          inflowDaysCol: string;
          limitUpCol: string;
          stageCol: string;
          scoreCol: string;
          actionCol: string;
          signalCol: string;
          highAvgCol: string;
          lowAvgCol: string;
          positionKeyCol: string;
          codeCol: string;
          nameCol: string;
          priceCol: string;
          amountCol: string;
          positionGainCol: string;
          highLaggardsLabel: string;
          lowStartersLabel: string;
          expandEmpty: string;
          switchEmpty: string;
          stage_start: string;
          stage_ferment: string;
          stage_climax: string;
          stage_ebb: string;
          stage_observe: string;
          action_attack: string;
          action_ambush: string;
          action_avoid: string;
          action_watch: string;
          signal_switching: string;
          signal_split: string;
          signal_resonance: string;
          signal_unknown: string;
          recentBoardsLabel: string;
          tomorrowBoardsLabel: string;
          switchSignalsLabel: string;
          themeHeatTitle: string;
          themeCol: string;
          positionCol: string;
          themeStatus_gathering: string;
          themeStatus_active: string;
          themeStatus_hot: string;
          themeStatus_cooling: string;
          themeStatus_flat: string;
          themeHeatLabel: string;
        };
      };
      };
  form: {
    required: string;
      userName: FormMsg;
        phone: FormMsg;
        pwd: FormMsg;
        confirmPwd: FormMsg;
        code: FormMsg;
        email: FormMsg;
      };
      dropdown: Record<Global.DropdownKey, string>;
      icon: {
        themeConfig: string;
        themeSchema: string;
        lang: string;
        fullscreen: string;
        fullscreenExit: string;
        reload: string;
        collapse: string;
        expand: string;
        pin: string;
        unpin: string;
      };
      datatable: {
        itemCount: string;
        fixed: {
          left: string;
          right: string;
          unFixed: string;
        };
      };
      notification: {
        title: string;
        tooltip: string;
        markAllAsRead: string;
        noNotifications: string;
        markAllReadSuccess: string;
        priority: {
          low: string;
          normal: string;
          high: string;
          urgent: string;
        };
      };
      exportTask: {
        title: string;
        tooltip: string;
        taskName: string;
        moduleKey: string;
        status: {
          title: string;
          pending: string;
          processing: string;
          completed: string;
          failed: string;
        };
        totalRows: string;
        fileSize: string;
        errorMessage: string;
        createdAt: string;
        finishedAt: string;
        noRecords: string;
        viewAll: string;
        asyncExport: string;
        submitSuccess: string;
        submitFailed: string;
        downloadFailed: string;
      };
    };

    type GetI18nKey<T extends Record<string, unknown>, K extends keyof T = keyof T> = K extends string
      ? T[K] extends Record<string, unknown>
        ? `${K}.${GetI18nKey<T[K]>}`
        : K
      : never;

    type I18nKey = GetI18nKey<Schema>;

    type TranslateOptions<Locales extends string> = import('vue-i18n').TranslateOptions<Locales>;

    interface $T {
      (key: I18nKey): string;
      (key: I18nKey, plural: number, options?: TranslateOptions<LangType>): string;
      (key: I18nKey, defaultMsg: string, options?: TranslateOptions<I18nKey>): string;
      (key: I18nKey, list: unknown[], options?: TranslateOptions<I18nKey>): string;
      (key: I18nKey, list: unknown[], plural: number): string;
      (key: I18nKey, list: unknown[], defaultMsg: string): string;
      (key: I18nKey, named: Record<string, unknown>, options?: TranslateOptions<LangType>): string;
      (key: I18nKey, named: Record<string, unknown>, plural: number): string;
      (key: I18nKey, named: Record<string, unknown>, defaultMsg: string): string;
    }
  }

  /** Service namespace */
  namespace Service {
    /** Other baseURL key */
    type OtherBaseURLKey = 'demo';

    interface ServiceConfigItem {
      /** The backend service base url */
      baseURL: string;
      /** The proxy pattern of the backend service base url */
      proxyPattern: string;
    }

    interface OtherServiceConfigItem extends ServiceConfigItem {
      key: OtherBaseURLKey;
    }

    /** The backend service config */
    interface ServiceConfig extends ServiceConfigItem {
      /** Other backend service config */
      other: OtherServiceConfigItem[];
    }

    interface SimpleServiceConfig extends Pick<ServiceConfigItem, 'baseURL'> {
      other: Record<OtherBaseURLKey, string>;
    }

    /** The backend service response data */
    type Response<T = unknown> = {
      /** The backend service response code */
      code: string;
      /** The backend service response message */
      msg: string;
      /** The backend service response data */
      data: T;
      /** The backend service request id */
      requestId?: string;
      /** The backend service error code */
      error_code?: string;
    };

    /** The demo backend service response data */
    type DemoResponse<T = unknown> = {
      /** The backend service response code */
      status: string;
      /** The backend service response message */
      message: string;
      /** The backend service response data */
      result: T;
    };
  }
}
