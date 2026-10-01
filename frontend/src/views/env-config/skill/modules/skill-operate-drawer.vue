<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { useVModel } from '@vueuse/core';
import type { FormItemRule } from 'naive-ui';
import {
  NButton,
  NDrawer,
  NDrawerContent,
  NForm,
  NFormItemGi,
  NGrid,
  NInput,
  NInputNumber,
  NSpace,
  NSwitch,
  useMessage
} from 'naive-ui';
import { fetchCreateSkill, fetchUpdateSkill } from '@/service/api';
import { $t } from '@/locales';

defineOptions({ name: 'SkillOperateDrawer' });

interface Props {
  visible: boolean;
  operateType: Api.OperateType;
  rowData?: Api.Skill.Skill | null;
}

const props = defineProps<Props>();
const emit = defineEmits<{
  'update:visible': [visible: boolean];
  submitted: [];
}>();

const message = useMessage();
const visible = useVModel(props, 'visible');

const drawerTitle = computed(() =>
  props.operateType === 'add' ? $t('page.manage.skill.addSkill') : $t('page.manage.skill.editSkill')
);

const formRef = ref();

const CODE_PATTERN = /^[a-z][a-z0-9_]*$/;

const formRules = {
  code: [
    { required: true, message: $t('form.required'), trigger: 'blur' },
    {
      validator: (_rule: FormItemRule, value: string) => {
        if (value && !CODE_PATTERN.test(value)) {
          return new Error($t('page.manage.skill.form.codeInvalid'));
        }
        return true;
      },
      trigger: 'blur'
    }
  ],
  name: { required: true, message: $t('form.required'), trigger: 'blur' },
  content: { required: true, message: $t('form.required'), trigger: 'blur' }
};

const defaultFormValue = {
  code: '',
  name: '',
  description: '',
  content: '',
  status: true,
  sort: 0
};

const form = reactive({ ...defaultFormValue });

watch(
  () => props.visible,
  val => {
    if (val) {
      if (props.operateType === 'edit' && props.rowData) {
        form.code = props.rowData.code;
        form.name = props.rowData.name;
        form.description = props.rowData.description || '';
        form.content = props.rowData.content;
        form.status = props.rowData.status === '1';
        form.sort = props.rowData.sort;
      } else {
        Object.assign(form, defaultFormValue);
      }
    }
  }
);

async function handleSubmit() {
  try {
    await formRef.value?.validate();
  } catch {
    return;
  }
  try {
    if (props.operateType === 'add') {
      const payload: Api.Skill.CreatePayload = {
        code: form.code,
        name: form.name,
        content: form.content,
        description: form.description || null,
        status: form.status,
        sort: form.sort
      };
      await fetchCreateSkill(payload);
      message.success($t('common.addSuccess'));
    } else if (props.operateType === 'edit' && props.rowData) {
      const payload: Api.Skill.UpdatePayload = {
        name: form.name,
        content: form.content,
        description: form.description || null,
        status: form.status,
        sort: form.sort
      };
      await fetchUpdateSkill(props.rowData.id, payload);
      message.success($t('common.updateSuccess'));
    }
    emit('submitted');
    visible.value = false;
  } catch (error) {
    console.error('提交失败:', error);
  }
}
</script>

<template>
  <NDrawer v-model:show="visible" :width="560">
    <NDrawerContent :title="drawerTitle" closable>
      <NForm ref="formRef" :model="form" :rules="formRules" label-placement="top">
        <NGrid responsive="screen" item-responsive>
          <NFormItemGi span="24" :label="$t('page.manage.skill.code')" path="code">
            <NInput
              v-model:value="form.code"
              :disabled="operateType === 'edit'"
              :placeholder="$t('page.manage.skill.form.code')"
            />
          </NFormItemGi>
          <NFormItemGi span="24" :label="$t('page.manage.skill.name')" path="name">
            <NInput v-model:value="form.name" :placeholder="$t('page.manage.skill.form.name')" />
          </NFormItemGi>
          <NFormItemGi span="24" :label="$t('page.manage.skill.description')" path="description">
            <NInput v-model:value="form.description" :placeholder="$t('page.manage.skill.form.description')" />
          </NFormItemGi>
          <NFormItemGi span="24" :label="$t('page.manage.skill.content')" path="content">
            <NInput
              v-model:value="form.content"
              type="textarea"
              :rows="12"
              :placeholder="$t('page.manage.skill.form.content')"
            />
          </NFormItemGi>
          <NFormItemGi span="24 m:12" :label="$t('page.manage.skill.sort')" path="sort">
            <NInputNumber v-model:value="form.sort" :min="0" :max="9999" class="w-full" />
          </NFormItemGi>
          <NFormItemGi span="24 m:12" :label="$t('page.manage.skill.status')">
            <NSwitch v-model:value="form.status" />
          </NFormItemGi>
        </NGrid>
      </NForm>
      <template #footer>
        <NSpace>
          <NButton @click="visible = false">{{ $t('common.cancel') }}</NButton>
          <NButton type="primary" @click="handleSubmit">{{ $t('common.confirm') }}</NButton>
        </NSpace>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped></style>
