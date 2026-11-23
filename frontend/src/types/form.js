/** @typedef {{key:string,label:string,type:string,required?:boolean,min?:number,max?:number,help?:string,example?:string|number,default?:string|number,choices?:string[]}} Field */
export const formValues = (form, fields) => {
  const data = new FormData(form);
  return Object.fromEntries(fields.flatMap(field => {
    const value = data.get(field.key);
    return value === null || value === '' ? [] : [[field.key, field.type === 'number' || field.type === 'integer' ? Number(value) : value]];
  }));
};
