import { esc } from '../../utils/html.js';

const optionValue = choice => typeof choice === 'string' ? choice : choice.value;
const optionLabel = choice => typeof choice === 'string' ? choice : (choice.label ?? choice.value);

export function fieldControl(field, defaults = false) {
  const {key, label, type, min, max, help, example, choices} = field;
  const value = defaults ? (field.default ?? '') : '';
  const required = field.required === false ? '' : 'required';
  const attributes = `name="${esc(key)}" ${required}`;
  let control;
  if (type === 'choice') {
    control = `<select ${attributes}><option value="">请选择</option>${choices.map(choice => `<option value="${esc(optionValue(choice))}" ${optionValue(choice) === value ? 'selected' : ''}>${esc(optionLabel(choice))}</option>`).join('')}</select>`;
  } else {
    const range = `${min !== undefined ? `min="${esc(min)}"` : ''} ${max !== undefined ? `max="${esc(max)}"` : ''}`;
    const inputType = ['integer','number'].includes(type) ? 'number' : type === 'date' ? 'date' : 'text';
    const step = inputType === 'number' ? `step="${type === 'integer' ? '1' : 'any'}"` : '';
    control = `<input type="${inputType}" ${attributes} ${range} ${step} value="${esc(value)}" placeholder="${esc(example ?? '')}">`;
  }
  return `<label class="field"><span>${esc(label)}</span>${control}${help ? `<small>${esc(help)}</small>` : ''}</label>`;
}

export const formError = '<div class="form-error" role="alert" hidden></div>';
